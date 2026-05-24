from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_shipment import EmsShippingRecord
from app.services import affiliate_wallet as affiliate_svc

_EMS_DELIVERED_PHASES = frozenset({"delivered", "cod_collected", "cod_settled"})
_EMS_IN_TRANSIT_PHASES = frozenset({"posted", "in_transit", "out_for_delivery"})

DeliveryBucket = Literal["returned", "delivered", "in_transit", "pending"]
CodBucket = Literal["paid", "returned_unpaid", "delivered_unpaid", "in_transit_unpaid", "pending_unpaid"]


def _is_returned(*, order_status: str | None, ems_status: str | None) -> bool:
    if (order_status or "").strip().lower() == OrderStatus.RETURNED.value:
        return True
    text = (ems_status or "").lower()
    if not text:
        return False
    markers = (
        "phát hoàn",
        "chuyển hoàn",
        "hoàn cho người gửi",
        "từ chối nhận hàng",
        "return to sender",
        "returned",
    )
    return any(m in text for m in markers)


def _is_delivered(*, ems_phase: str | None, ems_status: str | None) -> bool:
    phase = (ems_phase or "").strip().lower()
    if phase in _EMS_DELIVERED_PHASES:
        return True
    text = (ems_status or "").lower()
    return "phát thành công" in text and "phát hoàn" not in text


def _is_in_transit(*, ems_phase: str | None, ems_status: str | None) -> bool:
    phase = (ems_phase or "").strip().lower()
    if phase in _EMS_IN_TRANSIT_PHASES:
        return True
    text = (ems_status or "").lower()
    markers = ("vận chuyển", "giao bưu tá", "đến bưu cục", "chấp nhận gửi", "out for delivery")
    return any(m in text for m in markers)


def _delivery_bucket(record: EmsShippingRecord) -> DeliveryBucket:
    if _is_returned(order_status=record.order_status, ems_status=record.ems_status):
        return "returned"
    if _is_delivered(ems_phase=record.ems_phase, ems_status=record.ems_status):
        return "delivered"
    if _is_in_transit(ems_phase=record.ems_phase, ems_status=record.ems_status):
        return "in_transit"
    return "pending"


def _has_cod(record: EmsShippingRecord) -> bool:
    try:
        return record.cod_amount is not None and int(record.cod_amount) > 0
    except (TypeError, ValueError):
        return False


def _is_cod_paid(record: EmsShippingRecord) -> bool:
    if record.cod_paid_amount is not None:
        return True
    return (record.cod_settlement_status or "").strip().lower() == "matched"


def _cod_bucket(record: EmsShippingRecord, delivery: DeliveryBucket) -> CodBucket | None:
    if not _has_cod(record):
        return None
    if _is_cod_paid(record):
        return "paid"
    if delivery == "returned":
        return "returned_unpaid"
    if delivery == "delivered":
        return "delivered_unpaid"
    if delivery == "in_transit":
        return "in_transit_unpaid"
    return "pending_unpaid"


def get_shipping_operations_stats(db: Session) -> dict[str, Any]:
    """Thống kê theo bảng EMS — các nhóm loại trừ lẫn nhau, cộng đúng tổng dòng."""
    records = db.query(EmsShippingRecord).all()

    delivery_counts: dict[DeliveryBucket, int] = {
        "returned": 0,
        "delivered": 0,
        "in_transit": 0,
        "pending": 0,
    }
    cod_counts: dict[CodBucket, int] = {
        "paid": 0,
        "returned_unpaid": 0,
        "delivered_unpaid": 0,
        "in_transit_unpaid": 0,
        "pending_unpaid": 0,
    }
    cod_delivered_unpaid_total = 0
    cod_in_transit_unpaid_total = 0
    cod_paid_total = 0
    shop_linked_count = 0
    shop_return_received_count = 0
    freight_unsettled_count = 0

    for record in records:
        delivery = _delivery_bucket(record)
        delivery_counts[delivery] += 1

        if record.order_id is not None:
            shop_linked_count += 1
        if (record.order_status or "").strip().lower() == OrderStatus.RETURNED.value:
            shop_return_received_count += 1

        if (
            record.freight_settled_at is None
            and (record.ems_tracking_code or "").strip()
            and delivery != "returned"
        ):
            freight_unsettled_count += 1

        cod_bucket = _cod_bucket(record, delivery)
        if cod_bucket is None:
            continue
        cod_counts[cod_bucket] += 1
        cod_amt = int(record.cod_amount or 0)
        if cod_bucket == "delivered_unpaid":
            cod_delivered_unpaid_total += cod_amt
        elif cod_bucket == "in_transit_unpaid":
            cod_in_transit_unpaid_total += cod_amt
        elif cod_bucket == "paid":
            cod_paid_total += int(record.cod_paid_amount or cod_amt)

    total_ems_records = len(records)
    total_with_cod = sum(cod_counts.values())

    shop_shipping_orders = int(
        db.query(func.count(Order.id)).filter(Order.status == OrderStatus.SHIPPING.value).scalar() or 0
    )
    shop_delivered_orders = int(
        db.query(func.count(Order.id))
        .filter(Order.status.in_((OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value)))
        .scalar()
        or 0
    )
    shop_returned_orders = int(
        db.query(func.count(Order.id)).filter(Order.status == OrderStatus.RETURNED.value).scalar() or 0
    )

    return {
        "total_ems_records": total_ems_records,
        "total_with_cod": total_with_cod,
        "in_transit_count": delivery_counts["in_transit"],
        "delivered_count": delivery_counts["delivered"],
        "returned_count": delivery_counts["returned"],
        "pending_status_count": delivery_counts["pending"],
        "cod_in_transit_unpaid_count": cod_counts["in_transit_unpaid"],
        "cod_delivered_unpaid_count": cod_counts["delivered_unpaid"],
        "cod_paid_count": cod_counts["paid"],
        "cod_returned_unpaid_count": cod_counts["returned_unpaid"],
        "cod_pending_unpaid_count": cod_counts["pending_unpaid"],
        "cod_in_transit_unpaid_total": cod_in_transit_unpaid_total,
        "cod_delivered_unpaid_total": cod_delivered_unpaid_total,
        "cod_paid_total": cod_paid_total,
        "shop_linked_count": shop_linked_count,
        "shop_return_received_count": shop_return_received_count,
        "freight_unsettled_count": freight_unsettled_count,
        "shop_shipping_orders": shop_shipping_orders,
        "shop_delivered_orders": shop_delivered_orders,
        "shop_returned_orders": shop_returned_orders,
        # Legacy aliases
        "shipping_orders": delivery_counts["in_transit"],
        "delivered_success_orders": delivery_counts["delivered"],
        "returned_orders": shop_return_received_count,
        "cod_success_unpaid_count": cod_counts["delivered_unpaid"],
        "cod_success_unpaid_total": cod_delivered_unpaid_total,
        "cod_success_paid_count": cod_counts["paid"],
        "cod_success_paid_total": cod_paid_total,
        "shipping_cod_unpaid_count": cod_counts["in_transit_unpaid"],
    }


_OPS_BUCKET_LABELS: dict[str, str] = {
    "total": "Tổng vận đơn",
    "in_transit": "Đang giao",
    "delivered": "Giao thành công",
    "returned": "Hoàn hàng",
    "pending": "Chưa rõ EMS",
    "has_cod": "Có COD",
    "cod_in_transit_unpaid": "COD đang giao · chưa trả",
    "cod_delivered_unpaid": "COD giao OK · chưa trả",
    "cod_paid": "COD đã trả",
    "cod_returned_unpaid": "COD hoàn · chưa trả",
    "cod_pending_unpaid": "COD chưa rõ trạng thái",
    "freight_unsettled": "Chưa đối soát cước",
    "shop_linked": "Ghép đơn shop",
    "shop_return_received": "Hoàn · shop đã nhận",
    "shop_shipping": "Đơn shop đang giao",
}

_VALID_OPS_BUCKETS = frozenset(_OPS_BUCKET_LABELS.keys())


def _matches_ops_bucket(record: EmsShippingRecord, bucket: str) -> bool:
    delivery = _delivery_bucket(record)
    cod_bucket = _cod_bucket(record, delivery)

    if bucket == "total":
        return True
    if bucket == "in_transit":
        return delivery == "in_transit"
    if bucket == "delivered":
        return delivery == "delivered"
    if bucket == "returned":
        return delivery == "returned"
    if bucket == "pending":
        return delivery == "pending"
    if bucket == "has_cod":
        return cod_bucket is not None
    if bucket == "cod_in_transit_unpaid":
        return cod_bucket == "in_transit_unpaid"
    if bucket == "cod_delivered_unpaid":
        return cod_bucket == "delivered_unpaid"
    if bucket == "cod_paid":
        return cod_bucket == "paid"
    if bucket == "cod_returned_unpaid":
        return cod_bucket == "returned_unpaid"
    if bucket == "cod_pending_unpaid":
        return cod_bucket == "pending_unpaid"
    if bucket == "freight_unsettled":
        return (
            record.freight_settled_at is None
            and bool((record.ems_tracking_code or "").strip())
            and delivery != "returned"
        )
    if bucket == "shop_linked":
        return record.order_id is not None
    if bucket == "shop_return_received":
        return (record.order_status or "").strip().lower() == OrderStatus.RETURNED.value
    if bucket == "shop_shipping":
        return (record.order_status or "").strip().lower() == OrderStatus.SHIPPING.value
    return False


def list_operations_bucket_records(
    db: Session,
    bucket: str,
    *,
    skip: int = 0,
    limit: int = 25,
) -> dict[str, Any]:
    from app.services.ems_shipment_import import _enrich_row_from_live_order, _record_to_dict

    key = (bucket or "").strip().lower()
    if key not in _VALID_OPS_BUCKETS:
        raise ValueError(f"Nhóm thống kê không hợp lệ: {bucket}")

    skip = max(0, int(skip or 0))
    limit = max(1, min(int(limit or 25), 100))

    records = (
        db.query(EmsShippingRecord)
        .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
        .all()
    )
    matched = [record for record in records if _matches_ops_bucket(record, key)]
    total = len(matched)
    page_records = matched[skip : skip + limit]
    rows = [_enrich_row_from_live_order(db, _record_to_dict(record)) for record in page_records]

    return {
        "ok": True,
        "bucket": key,
        "bucket_label": _OPS_BUCKET_LABELS[key],
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total,
            "filtered_total": total,
        },
        "rows": rows,
    }


def admin_approve_return_received(
    db: Session,
    order_id: int,
    *,
    admin_id: int,
    note: str | None = None,
) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("Order not found")

    status_val = getattr(order.status, "value", order.status)
    if status_val == OrderStatus.RETURNED.value:
        raise ValueError("Đơn đã được ghi nhận hoàn hàng.")
    if status_val == OrderStatus.CANCELLED.value:
        raise ValueError("Đơn đã hủy — không thể duyệt hoàn hàng.")
    if status_val not in (
        OrderStatus.SHIPPING.value,
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
    ):
        raise ValueError("Chỉ duyệt hoàn hàng khi đơn đang giao hoặc đã giao thành công.")

    old_status = status_val
    now = datetime.now()
    order.status = OrderStatus.RETURNED.value
    order.returned_at = now
    if note:
        prefix = f"\n[Nhận hàng hoàn {now.strftime('%d/%m/%Y %H:%M')}] "
        order.admin_notes = ((order.admin_notes or "") + prefix + note.strip()).strip()
    order.processed_by = admin_id
    order.updated_at = now

    affiliate_svc.handle_order_status_change(db, order, old_status, OrderStatus.RETURNED.value)

    ems_records = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.order_id == order.id)
        .all()
    )
    for record in ems_records:
        record.order_status = OrderStatus.RETURNED.value
        msg = record.sync_message or ""
        if "Đơn hoàn hàng" not in msg:
            record.sync_message = (msg + " · Đơn hoàn hàng — shop đã nhận lại.").strip(" ·")

    db.commit()
    db.refresh(order)
    return order
