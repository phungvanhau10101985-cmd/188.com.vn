from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_shipment import EmsShippingRecord
from app.services import affiliate_wallet as affiliate_svc

_EMS_DELIVERED_PHASES = ("delivered", "cod_collected", "cod_settled")
_SUCCESS_ORDER_STATUSES = (
    OrderStatus.DELIVERED.value,
    OrderStatus.COMPLETED.value,
)
_ACTIVE_COD_STATUSES = (
    OrderStatus.SHIPPING.value,
    OrderStatus.DELIVERED.value,
    OrderStatus.COMPLETED.value,
)


def get_shipping_operations_stats(db: Session) -> dict[str, Any]:
    shipping_orders = (
        db.query(func.count(Order.id))
        .filter(Order.status == OrderStatus.SHIPPING.value)
        .scalar()
        or 0
    )
    delivered_success_orders = (
        db.query(func.count(Order.id))
        .filter(Order.status.in_(_SUCCESS_ORDER_STATUSES))
        .scalar()
        or 0
    )
    returned_orders = (
        db.query(func.count(Order.id))
        .filter(Order.status == OrderStatus.RETURNED.value)
        .scalar()
        or 0
    )

    ems_base = db.query(EmsShippingRecord).filter(EmsShippingRecord.cod_amount.isnot(None))
    ems_base = ems_base.filter(EmsShippingRecord.cod_amount > 0)

    not_closed = or_(
        EmsShippingRecord.order_status.is_(None),
        ~EmsShippingRecord.order_status.in_(
            (OrderStatus.RETURNED.value, OrderStatus.CANCELLED.value)
        ),
    )

    delivered_like = or_(
        EmsShippingRecord.ems_phase.in_(_EMS_DELIVERED_PHASES),
        EmsShippingRecord.order_status.in_(_SUCCESS_ORDER_STATUSES),
    )

    cod_success_unpaid_q = ems_base.filter(
        EmsShippingRecord.cod_paid_amount.is_(None),
        delivered_like,
        not_closed,
    )
    cod_success_paid_q = ems_base.filter(EmsShippingRecord.cod_paid_amount.isnot(None))

    cod_success_unpaid_count = cod_success_unpaid_q.count()
    cod_success_paid_count = cod_success_paid_q.count()

    cod_success_unpaid_total = int(
        cod_success_unpaid_q.with_entities(func.coalesce(func.sum(EmsShippingRecord.cod_amount), 0)).scalar() or 0
    )
    cod_success_paid_total = int(
        cod_success_paid_q.with_entities(func.coalesce(func.sum(EmsShippingRecord.cod_paid_amount), 0)).scalar() or 0
    )

    shipping_with_cod = (
        db.query(func.count(EmsShippingRecord.id))
        .filter(
            EmsShippingRecord.cod_amount.isnot(None),
            EmsShippingRecord.cod_amount > 0,
            or_(
                EmsShippingRecord.order_status == OrderStatus.SHIPPING.value,
                EmsShippingRecord.order_status.is_(None),
            ),
            EmsShippingRecord.cod_paid_amount.is_(None),
            not_closed,
        )
        .scalar()
        or 0
    )

    freight_unsettled = (
        db.query(func.count(EmsShippingRecord.id))
        .filter(
            EmsShippingRecord.freight_settled_at.is_(None),
            EmsShippingRecord.ems_tracking_code.isnot(None),
            or_(
                EmsShippingRecord.order_status.in_(_ACTIVE_COD_STATUSES),
                EmsShippingRecord.order_status.is_(None),
            ),
            not_closed,
        )
        .scalar()
        or 0
    )

    return {
        "shipping_orders": int(shipping_orders),
        "delivered_success_orders": int(delivered_success_orders),
        "returned_orders": int(returned_orders),
        "cod_success_unpaid_count": int(cod_success_unpaid_count),
        "cod_success_unpaid_total": cod_success_unpaid_total,
        "cod_success_paid_count": int(cod_success_paid_count),
        "cod_success_paid_total": cod_success_paid_total,
        "shipping_cod_unpaid_count": int(shipping_with_cod),
        "freight_unsettled_count": int(freight_unsettled),
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
