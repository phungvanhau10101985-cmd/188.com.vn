from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import crud
from app.models.order import Order, OrderStatus
from app.models.order_shipment import EmsShippingRecord
from app.services import affiliate_wallet as affiliate_svc
from app.services.ems_shipment_import import (
    extract_warehouse_sku_from_ems_label,
    looks_like_recipient_not_sku,
)

_VN_TZ = timezone(timedelta(hours=7))
TimelineGranularity = Literal["year", "month", "week", "day"]
_TIMELINE_GRANULARITIES = frozenset({"year", "month", "week", "day"})
_TIMELINE_DEFAULT_LIMITS: dict[str, int] = {
    "year": 20,
    "month": 36,
    "week": 52,
    "day": 90,
}

_EMS_DELIVERED_PHASES = frozenset({"delivered", "cod_collected", "cod_settled"})
_EMS_IN_TRANSIT_PHASES = frozenset({"posted", "in_transit", "out_for_delivery"})

DeliveryBucket = Literal["return_pending_shop", "return_shop_received", "delivered", "in_transit", "pending"]
CodBucket = Literal["paid", "returned_unpaid", "delivered_unpaid", "in_transit_unpaid", "pending_unpaid"]

RETURN_PENDING_SHOP_LABEL = "Đơn hoàn chưa trả shop"
RETURN_SHOP_RECEIVED_LABEL = "Đơn hoàn đã trả shop"


def _is_shop_return_received(*, order_status: str | None) -> bool:
    return (order_status or "").strip().lower() == OrderStatus.RETURNED.value


def _is_ems_return_pending_shop(*, ems_status: str | None) -> bool:
    """EMS đã duyệt / báo hoàn — hàng chưa về shop (đơn shop chưa RETURNED)."""
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


def return_to_shop_label(*, order_status: str | None, ems_status: str | None) -> str | None:
    if _is_shop_return_received(order_status=order_status):
        return RETURN_SHOP_RECEIVED_LABEL
    if _is_ems_return_pending_shop(ems_status=ems_status):
        return RETURN_PENDING_SHOP_LABEL
    return None


def _is_delivered(*, ems_phase: str | None, ems_status: str | None) -> bool:
    phase = (ems_phase or "").strip().lower()
    if phase in _EMS_DELIVERED_PHASES:
        return True
    text = (ems_status or "").lower()
    compact = text.replace(" ", "")
    if "[cod]đãthutiền" in compact or "đãthutiềnbưutá" in compact:
        return True
    if "[cod]trảtiền" in compact or "trảtiềnchongườigửi" in compact:
        return True
    return "phát thành công" in text and "phát hoàn" not in text


def _is_in_transit(*, ems_phase: str | None, ems_status: str | None) -> bool:
    phase = (ems_phase or "").strip().lower()
    if phase in _EMS_IN_TRANSIT_PHASES:
        return True
    text = (ems_status or "").lower()
    markers = ("vận chuyển", "giao bưu tá", "đến bưu cục", "chấp nhận gửi", "out for delivery")
    return any(m in text for m in markers)


def _delivery_bucket(record: EmsShippingRecord) -> DeliveryBucket:
    if _is_shop_return_received(order_status=record.order_status):
        return "return_shop_received"
    if _is_ems_return_pending_shop(ems_status=record.ems_status):
        return "return_pending_shop"
    if _is_delivered(ems_phase=record.ems_phase, ems_status=record.ems_status):
        return "delivered"
    if (record.cod_settlement_status or "").strip().lower() == "matched":
        return "delivered"
    if _is_in_transit(ems_phase=record.ems_phase, ems_status=record.ems_status):
        return "in_transit"
    return "pending"


def _has_cod(record: EmsShippingRecord) -> bool:
    try:
        return record.cod_amount is not None and int(record.cod_amount) > 0
    except (TypeError, ValueError):
        return False


def _record_cod_amount(record: EmsShippingRecord) -> int:
    try:
        return max(0, int(record.cod_amount or 0))
    except (TypeError, ValueError):
        return 0


def _is_cod_paid(record: EmsShippingRecord) -> bool:
    """EMS đã trả tiền thu hộ về shop — chỉ khi import file đối soát COD khớp."""
    return (record.cod_settlement_status or "").strip().lower() == "matched"


def _cod_bucket(record: EmsShippingRecord, delivery: DeliveryBucket) -> CodBucket | None:
    if not _has_cod(record):
        return None
    if _is_cod_paid(record):
        return "paid"
    if delivery in ("return_pending_shop", "return_shop_received"):
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
        "return_pending_shop": 0,
        "return_shop_received": 0,
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
    cod_returned_unpaid_total = 0
    cod_pending_unpaid_total = 0
    total_cod_sum = 0
    total_cod_amount = 0
    delivery_cod_totals: dict[DeliveryBucket, int] = {
        "return_pending_shop": 0,
        "return_shop_received": 0,
        "delivered": 0,
        "in_transit": 0,
        "pending": 0,
    }
    shop_linked_count = 0
    shop_return_received_count = 0
    freight_unsettled_count = 0

    for record in records:
        delivery = _delivery_bucket(record)
        delivery_counts[delivery] += 1
        cod_amt = _record_cod_amount(record)
        total_cod_sum += cod_amt
        delivery_cod_totals[delivery] += cod_amt
        if _has_cod(record):
            total_cod_amount += cod_amt

        if record.order_id is not None:
            shop_linked_count += 1
        if (record.order_status or "").strip().lower() == OrderStatus.RETURNED.value:
            shop_return_received_count += 1

        if (
            record.freight_settled_at is None
            and (record.ems_tracking_code or "").strip()
            and delivery not in ("return_pending_shop", "return_shop_received")
        ):
            freight_unsettled_count += 1

        cod_bucket = _cod_bucket(record, delivery)
        if cod_bucket is None:
            continue
        cod_counts[cod_bucket] += 1
        if cod_bucket == "delivered_unpaid":
            cod_delivered_unpaid_total += cod_amt
        elif cod_bucket == "in_transit_unpaid":
            cod_in_transit_unpaid_total += cod_amt
        elif cod_bucket == "returned_unpaid":
            cod_returned_unpaid_total += cod_amt
        elif cod_bucket == "pending_unpaid":
            cod_pending_unpaid_total += cod_amt
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
        "returned_count": delivery_counts["return_pending_shop"],
        "return_shop_received_count": delivery_counts["return_shop_received"],
        "pending_status_count": delivery_counts["pending"],
        "cod_in_transit_unpaid_count": cod_counts["in_transit_unpaid"],
        "cod_delivered_unpaid_count": cod_counts["delivered_unpaid"],
        "cod_paid_count": cod_counts["paid"],
        "cod_returned_unpaid_count": cod_counts["returned_unpaid"],
        "cod_pending_unpaid_count": cod_counts["pending_unpaid"],
        "cod_in_transit_unpaid_total": cod_in_transit_unpaid_total,
        "cod_delivered_unpaid_total": cod_delivered_unpaid_total,
        "cod_paid_total": cod_paid_total,
        "cod_returned_unpaid_total": cod_returned_unpaid_total,
        "cod_pending_unpaid_total": cod_pending_unpaid_total,
        "total_cod_sum": total_cod_sum,
        "total_cod_amount": total_cod_amount,
        "in_transit_cod_total": delivery_cod_totals["in_transit"],
        "delivered_cod_total": delivery_cod_totals["delivered"],
        "returned_cod_total": delivery_cod_totals["return_pending_shop"],
        "return_shop_received_cod_total": delivery_cod_totals["return_shop_received"],
        "pending_cod_total": delivery_cod_totals["pending"],
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
        # returned_count = EMS hoàn, chưa shop xác nhận; shop_return_received_count = shop đã nhận hoàn
        "cod_success_unpaid_count": cod_counts["delivered_unpaid"],
        "cod_success_unpaid_total": cod_delivered_unpaid_total,
        "cod_success_paid_count": cod_counts["paid"],
        "cod_success_paid_total": cod_paid_total,
        "shipping_cod_unpaid_count": cod_counts["in_transit_unpaid"],
    }


def _to_vn_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_VN_TZ)


def _vn_today() -> date:
    return datetime.now(_VN_TZ).date()


def _parse_iso_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Ngày không hợp lệ: {value}") from exc


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


_TIMELINE_PRESETS = frozenset({"this_week", "last_week", "this_month", "last_month"})


def _resolve_timeline_filter(
    *,
    preset: str | None = None,
    year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[date | None, date | None, str | None]:
    key = (preset or "").strip().lower()
    if key:
        if key not in _TIMELINE_PRESETS:
            raise ValueError("preset phải là this_week, last_week, this_month hoặc last_month.")
        today = _vn_today()
        if key == "this_week":
            start = today - timedelta(days=today.weekday())
            end = start + timedelta(days=6)
            return start, end, f"Tuần này ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
        if key == "last_week":
            this_monday = today - timedelta(days=today.weekday())
            start = this_monday - timedelta(days=7)
            end = start + timedelta(days=6)
            return start, end, f"Tuần trước ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
        if key == "this_month":
            start, end = _month_bounds(today.year, today.month)
            return start, end, f"Tháng này ({today.month:02d}/{today.year})"
        prev_year = today.year - 1 if today.month == 1 else today.year
        prev_month = 12 if today.month == 1 else today.month - 1
        start, end = _month_bounds(prev_year, prev_month)
        return start, end, f"Tháng trước ({prev_month:02d}/{prev_year})"

    if year is not None:
        y = int(year)
        if y < 1970 or y > 2100:
            raise ValueError("Năm không hợp lệ.")
        start = date(y, 1, 1)
        end = date(y, 12, 31)
        return start, end, str(y)

    parsed_from = _parse_iso_date(date_from) if date_from else None
    parsed_to = _parse_iso_date(date_to) if date_to else None
    if parsed_from or parsed_to:
        start = parsed_from or parsed_to
        end = parsed_to or parsed_from
        assert start is not None and end is not None
        if start > end:
            start, end = end, start
        if start == end:
            return start, end, start.strftime("%d/%m/%Y")
        return start, end, f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')}"

    return None, None, None


def _record_import_date(record: EmsShippingRecord) -> date | None:
    local_dt = _to_vn_datetime(record.created_at or record.updated_at)
    return local_dt.date() if local_dt else None


def _record_timeline_period_key(record: EmsShippingRecord, granularity: TimelineGranularity) -> str | None:
    local_dt = _to_vn_datetime(record.created_at or record.updated_at)
    if local_dt is None:
        return None
    return _timeline_period_key(local_dt, granularity)


def _timeline_period_key(local_dt: datetime, granularity: TimelineGranularity) -> str:
    if granularity == "year":
        return f"{local_dt.year:04d}"
    if granularity == "month":
        return f"{local_dt.year:04d}-{local_dt.month:02d}"
    if granularity == "week":
        iso = local_dt.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    return local_dt.date().isoformat()


def _timeline_period_bounds(
    period_key: str,
    granularity: TimelineGranularity,
) -> tuple[date, date, str]:
    if granularity == "year":
        year = int(period_key)
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        return start, end, str(year)

    if granularity == "month":
        year_s, month_s = period_key.split("-", 1)
        year = int(year_s)
        month = int(month_s)
        start = date(year, month, 1)
        if month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
        return start, end, f"{month:02d}/{year}"

    if granularity == "week":
        year_s, week_s = period_key.split("-W", 1)
        year = int(year_s)
        week = int(week_s)
        start = date.fromisocalendar(year, week, 1)
        end = date.fromisocalendar(year, week, 7)
        return start, end, f"Tuần {week:02d}/{year}"

    day = date.fromisoformat(period_key)
    return day, day, day.strftime("%d/%m/%Y")


def _empty_timeline_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "in_transit_count": 0,
        "delivered_count": 0,
        "returned_count": 0,
        "return_shop_received_count": 0,
        "pending_status_count": 0,
        "total_cod_sum": 0,
        "in_transit_cod_total": 0,
        "delivered_cod_total": 0,
        "returned_cod_total": 0,
        "return_shop_received_cod_total": 0,
        "pending_cod_total": 0,
        "total_with_cod": 0,
        "cod_in_transit_unpaid_count": 0,
        "cod_in_transit_unpaid_total": 0,
        "cod_delivered_unpaid_count": 0,
        "cod_delivered_unpaid_total": 0,
        "cod_returned_unpaid_count": 0,
        "cod_returned_unpaid_total": 0,
        "cod_paid_count": 0,
        "total_cod_amount": 0,
        "cod_paid_total": 0,
    }


def _accumulate_timeline_bucket(bucket: dict[str, Any], record: EmsShippingRecord) -> None:
    delivery = _delivery_bucket(record)
    bucket["total"] += 1
    cod_amt = _record_cod_amount(record)
    bucket["total_cod_sum"] += cod_amt
    delivery_cod_field = {
        "return_pending_shop": "returned_cod_total",
        "return_shop_received": "return_shop_received_cod_total",
        "delivered": "delivered_cod_total",
        "in_transit": "in_transit_cod_total",
        "pending": "pending_cod_total",
    }[delivery]
    bucket[delivery_cod_field] += cod_amt

    delivery_field = {
        "return_pending_shop": "returned_count",
        "return_shop_received": "return_shop_received_count",
        "delivered": "delivered_count",
        "in_transit": "in_transit_count",
        "pending": "pending_status_count",
    }[delivery]
    bucket[delivery_field] += 1

    cod_bucket = _cod_bucket(record, delivery)
    if cod_bucket is None:
        return
    bucket["total_with_cod"] += 1
    bucket["total_cod_amount"] += cod_amt
    if cod_bucket == "paid":
        bucket["cod_paid_count"] += 1
        try:
            bucket["cod_paid_total"] += int(record.cod_paid_amount or cod_amt)
        except (TypeError, ValueError):
            bucket["cod_paid_total"] += cod_amt
    elif cod_bucket == "delivered_unpaid":
        bucket["cod_delivered_unpaid_count"] += 1
        bucket["cod_delivered_unpaid_total"] += cod_amt
    elif cod_bucket == "in_transit_unpaid":
        bucket["cod_in_transit_unpaid_count"] += 1
        bucket["cod_in_transit_unpaid_total"] += cod_amt
    elif cod_bucket == "returned_unpaid":
        bucket["cod_returned_unpaid_count"] += 1
        bucket["cod_returned_unpaid_total"] += cod_amt


def get_shipping_timeline_stats(
    db: Session,
    *,
    granularity: str = "month",
    limit: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    preset: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Thống kê vận đơn EMS theo thời gian import (created_at, múi giờ VN)."""
    key = (granularity or "month").strip().lower()
    if key not in _TIMELINE_GRANULARITIES:
        raise ValueError("granularity phải là year, month, week hoặc day.")

    filter_start, filter_end, filter_label = _resolve_timeline_filter(
        preset=preset,
        year=year,
        date_from=date_from,
        date_to=date_to,
    )

    max_items = limit if limit is not None else _TIMELINE_DEFAULT_LIMITS[key]
    max_items = max(1, min(int(max_items), 200))

    records = db.query(EmsShippingRecord).order_by(EmsShippingRecord.created_at.desc()).all()
    available_years: set[int] = set()
    grouped: dict[str, dict[str, Any]] = {}

    for record in records:
        rec_date = _record_import_date(record)
        if rec_date is None:
            continue
        available_years.add(rec_date.year)
        if filter_start and rec_date < filter_start:
            continue
        if filter_end and rec_date > filter_end:
            continue

        local_dt = _to_vn_datetime(record.created_at or record.updated_at)
        if local_dt is None:
            continue
        period_key = _timeline_period_key(local_dt, key)  # type: ignore[arg-type]
        if period_key not in grouped:
            grouped[period_key] = _empty_timeline_bucket()
        _accumulate_timeline_bucket(grouped[period_key], record)

    sorted_keys = sorted(grouped.keys(), reverse=True)[:max_items]
    items: list[dict[str, Any]] = []
    totals = _empty_timeline_bucket()

    for period_key in sorted_keys:
        bucket = grouped[period_key]
        start, end, label = _timeline_period_bounds(period_key, key)  # type: ignore[arg-type]
        item = {
            "period_key": period_key,
            "period_label": label,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            **bucket,
        }
        items.append(item)
        for field in totals:
            totals[field] += int(bucket.get(field) or 0)

    return {
        "granularity": key,
        "timezone": "Asia/Ho_Chi_Minh",
        "date_field": "created_at",
        "limit": max_items,
        "filter_from": filter_start.isoformat() if filter_start else None,
        "filter_to": filter_end.isoformat() if filter_end else None,
        "filter_label": filter_label,
        "preset": (preset or "").strip().lower() or None,
        "year": int(year) if year is not None else None,
        "available_years": sorted(available_years, reverse=True),
        "items": items,
        "totals": totals,
    }


_OPS_BUCKET_LABELS: dict[str, str] = {
    "total": "Tổng vận đơn",
    "in_transit": "Đang giao",
    "delivered": "Giao thành công",
    "returned": "Đơn hoàn chưa trả shop",
    "return_pending_shop": "Đơn hoàn chưa trả shop",
    "return_shop_received": "Đơn hoàn đã trả shop",
    "pending": "Chưa rõ EMS",
    "has_cod": "Có COD",
    "cod_in_transit_unpaid": "COD đang giao · chưa trả",
    "cod_delivered_unpaid": "Giao OK · EMS chưa trả COD cho shop",
    "cod_paid": "COD EMS đã trả shop",
    "cod_returned_unpaid": "COD hoàn · chưa trả",
    "cod_pending_unpaid": "COD chưa rõ trạng thái",
    "freight_unsettled": "Chưa đối soát cước",
    "shop_linked": "Ghép đơn shop",
    "shop_return_received": "Đơn hoàn đã trả shop",
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
    if bucket == "returned" or bucket == "return_pending_shop":
        return delivery == "return_pending_shop"
    if bucket == "return_shop_received":
        return delivery == "return_shop_received"
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
            and delivery not in ("return_pending_shop", "return_shop_received")
        )
    if bucket == "shop_linked":
        return record.order_id is not None
    if bucket == "shop_return_received":
        return (record.order_status or "").strip().lower() == OrderStatus.RETURNED.value
    if bucket == "shop_shipping":
        return (record.order_status or "").strip().lower() == OrderStatus.SHIPPING.value
    return False


def list_timeline_bucket_records(
    db: Session,
    bucket: str,
    *,
    granularity: str = "week",
    period_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    preset: str | None = None,
    year: int | None = None,
    skip: int = 0,
    limit: int = 25,
) -> dict[str, Any]:
    from app.services.ems_shipment_import import _enrich_row_from_live_order, _record_to_dict

    key = (bucket or "").strip().lower()
    if key not in _VALID_OPS_BUCKETS:
        raise ValueError(f"Nhóm thống kê không hợp lệ: {bucket}")

    gran = (granularity or "week").strip().lower()
    if gran not in _TIMELINE_GRANULARITIES:
        raise ValueError("granularity phải là year, month, week hoặc day.")

    period = (period_key or "").strip() or None
    filter_start, filter_end, filter_label = _resolve_timeline_filter(
        preset=preset,
        year=year,
        date_from=date_from,
        date_to=date_to,
    )

    skip = max(0, int(skip or 0))
    limit = max(1, min(int(limit or 25), 100))

    records = (
        db.query(EmsShippingRecord)
        .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
        .all()
    )
    matched: list[EmsShippingRecord] = []

    for record in records:
        rec_date = _record_import_date(record)
        if rec_date is None:
            continue
        if filter_start and rec_date < filter_start:
            continue
        if filter_end and rec_date > filter_end:
            continue
        if period:
            record_period = _record_timeline_period_key(record, gran)  # type: ignore[arg-type]
            if record_period != period:
                continue
        if _matches_ops_bucket(record, key):
            matched.append(record)

    total = len(matched)
    page_records = matched[skip : skip + limit]
    rows = [_enrich_row_from_live_order(db, _record_to_dict(record)) for record in page_records]

    bucket_label = _OPS_BUCKET_LABELS[key]
    if period:
        _, _, period_label = _timeline_period_bounds(period, gran)  # type: ignore[arg-type]
        bucket_label = f"{bucket_label} — {period_label}"
    elif filter_label:
        bucket_label = f"{bucket_label} — {filter_label}"

    return {
        "ok": True,
        "bucket": key,
        "bucket_label": bucket_label,
        "period_key": period,
        "granularity": gran,
        "pagination": {
            "skip": skip,
            "limit": limit,
            "total": total,
            "filtered_total": total,
        },
        "rows": rows,
    }


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


def find_ems_record_by_token(db: Session, token: str) -> EmsShippingRecord | None:
    """Tra mã EMS, mã tham chiếu (cột A), ems_reference_code hoặc mã đơn shop trên dòng EMS."""
    t = (token or "").strip().upper()
    if not t or len(t) < 3:
        return None
    for column in (
        EmsShippingRecord.ems_tracking_code,
        EmsShippingRecord.reference_code,
        EmsShippingRecord.ems_reference_code,
        EmsShippingRecord.order_code,
    ):
        record = db.query(EmsShippingRecord).filter(column.ilike(t)).first()
        if record:
            return record
    return None


def _primary_ems_record_for_order(db: Session, order_id: int) -> EmsShippingRecord | None:
    return (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.order_id == order_id)
        .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
        .first()
    )


def _warehouse_sku_from_ems_record(record: EmsShippingRecord | None) -> str | None:
    """SKU từ cột H (product_code) — không dùng nhãn người nhận."""
    if record is None:
        return None
    raw = (getattr(record, "product_code", None) or "").strip()
    if not raw or looks_like_recipient_not_sku(raw):
        return None
    return extract_warehouse_sku_from_ems_label(raw)


def _ems_snapshot(record: EmsShippingRecord | None) -> dict[str, Any]:
    if record is None:
        return {"ems_status": None, "ems_phase": None, "ems_tracking_code": None}
    tracking = (record.ems_tracking_code or record.reference_code or "").strip() or None
    return {
        "ems_status": (record.ems_status or "").strip() or None,
        "ems_phase": (record.ems_phase or "").strip() or None,
        "ems_tracking_code": tracking,
    }


def _order_status_value(order: Order | None, *, record: EmsShippingRecord | None = None) -> str | None:
    if order is not None:
        val = getattr(order.status, "value", order.status)
        return str(val).strip() if val else None
    if record is not None and record.order_status:
        return str(record.order_status).strip() or None
    return None


def _resolve_shop_return_context(
    db: Session,
    *,
    raw: str,
    code: Optional[str],
) -> tuple[Optional[EmsShippingRecord], Optional[Order], str]:
    """Ghép vận đơn EMS + đơn shop từ mã nhập (EMS / tham chiếu / mã đơn)."""
    token = (raw or code or "").strip()
    display_code = (code or "").strip().upper() or None
    record = find_ems_record_by_token(db, token) if token else None
    order: Order | None = None

    if record:
        if not display_code:
            display_code = (record.order_code or "").strip().upper() or None
        if record.order_id:
            order = db.query(Order).filter(Order.id == record.order_id).first()
        if not order and display_code:
            order = crud.order.get_order_by_code(db, display_code)

    if not record and display_code:
        order = crud.order.get_order_by_code(db, display_code)
        if order:
            record = _primary_ems_record_for_order(db, order.id)

    if not display_code and record:
        display_code = (
            (record.order_code or record.reference_code or record.ems_tracking_code or token or "")
            .strip()
            .upper()
            or None
        )

    return record, order, display_code or ""


def _shop_already_received_return(*, order: Order | None, record: EmsShippingRecord | None) -> bool:
    if order is not None:
        status_val = getattr(order.status, "value", order.status)
        if _is_shop_return_received(order_status=status_val):
            return True
    if record is not None and _is_shop_return_received(order_status=record.order_status):
        return True
    return False


def evaluate_shop_return_entry(
    db: Session,
    entry: dict[str, Any],
    seen_codes: dict[str, int],
) -> dict[str, Any]:
    """
    Đánh giá một dòng nhập — không ghi DB.
    Hai trạng thái chính: ready_to_confirm (EMS hoàn, shop chưa xác nhận) và already_returned.
    """
    row_number = int(entry.get("row_number") or 0)
    raw = str(entry.get("raw") or "").strip()
    code = (entry.get("order_code") or "").strip().upper() or None

    def _row(**kwargs: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "row_number": row_number,
            "raw": raw,
            "order_code": code,
            "order_id": None,
            "ems_status": None,
            "ems_phase": None,
            "ems_tracking_code": None,
            "order_status": None,
            "can_confirm": False,
            "can_show_warehouse": False,
            "warehouse_sku": None,
            "ems_record_id": None,
        }
        base.update(kwargs)
        return base

    if not code and not raw:
        return _row(
            status="not_ready",
            message="Mã trống — nhập mã EMS, mã tham chiếu hoặc mã đơn.",
        )

    record, order, display_code = _resolve_shop_return_context(db, raw=raw, code=code)
    code = display_code or code
    dedupe_key = (code or raw).strip().upper()
    if dedupe_key in seen_codes:
        return _row(
            order_code=code or None,
            status="duplicate",
            message=f"Mã trùng trong danh sách (đã có ở dòng {seen_codes[dedupe_key]}).",
        )
    if dedupe_key:
        seen_codes[dedupe_key] = row_number
    snap = _ems_snapshot(record)
    order_status = _order_status_value(order, record=record)

    if _shop_already_received_return(order=order, record=record):
        return _row(
            order_code=code or None,
            order_id=order.id if order else None,
            order_status=order_status,
            status="already_returned",
            message="Shop đã xác nhận đã nhận hàng hoàn.",
            **snap,
        )

    if not record:
        return _row(
            order_code=code or None,
            status="not_ready",
            message="Không tìm thấy vận đơn EMS — nhập mã EMS, mã tham chiếu hoặc mã đơn.",
        )

    if not _is_ems_return_pending_shop(ems_status=record.ems_status):
        ems_label = (record.ems_status or "").strip() or "—"
        return _row(
            order_code=code or None,
            order_id=order.id if order else record.order_id,
            order_status=order_status,
            status="not_ready",
            message=(
                f"EMS chưa báo đơn hoàn (hiện tại: «{ems_label}»). "
                "Chỉ xác nhận khi EMS đã phát hoàn / chuyển hoàn."
            ),
            **snap,
        )

    if order:
        err = validate_shop_return_confirm(order)
        if err:
            return _row(
                order_code=code,
                order_id=order.id,
                order_status=order_status,
                ems_record_id=record.id,
                status=err[0],
                message=err[1],
                **snap,
            )

    wh_sku = _warehouse_sku_from_ems_record(record)
    msg = "EMS đã báo đơn hoàn — shop chưa xác nhận, có thể xác nhận đã nhận hàng."
    if not order:
        msg += " (Chưa có đơn shop trên web — chỉ ghi nhận trên vận đơn EMS.)"
    return _row(
        order_code=code or None,
        order_id=order.id if order else record.order_id,
        order_status=order_status,
        ems_record_id=record.id,
        status="ready_to_confirm",
        message=msg,
        can_confirm=True,
        can_show_warehouse=True,
        warehouse_sku=wh_sku,
        **snap,
    )


def preview_shop_returns(
    db: Session,
    entries: list[dict[str, Any]],
    *,
    source: str = "preview",
) -> dict[str, Any]:
    """Tra cứu trạng thái — không xác nhận, không commit."""
    seen_codes: dict[str, int] = {}
    rows_out = [evaluate_shop_return_entry(db, entry, seen_codes) for entry in entries]
    rows_out.sort(key=lambda r: (int(r.get("row_number") or 0), str(r.get("order_code") or "")))
    confirmable = sum(1 for r in rows_out if r.get("can_confirm"))
    warehouse_eligible = sum(1 for r in rows_out if r.get("can_show_warehouse"))
    already_returned_count = sum(1 for r in rows_out if r["status"] == "already_returned")
    error_count = len(rows_out) - confirmable - already_returned_count
    return {
        "ok": True,
        "preview": True,
        "source": source,
        "total_rows": len(entries),
        "confirmed_count": 0,
        "confirmable_count": confirmable,
        "warehouse_eligible_count": warehouse_eligible,
        "error_count": error_count,
        "not_found_count": sum(1 for r in rows_out if r["status"] == "not_found"),
        "invalid_code_count": sum(1 for r in rows_out if r["status"] == "invalid_code"),
        "already_returned_count": sum(1 for r in rows_out if r["status"] == "already_returned"),
        "invalid_status_count": sum(1 for r in rows_out if r["status"] == "invalid_status"),
        "duplicate_count": sum(1 for r in rows_out if r["status"] == "duplicate"),
        "ems_not_return_count": sum(1 for r in rows_out if r["status"] == "ems_not_return"),
        "ems_not_linked_count": sum(1 for r in rows_out if r["status"] == "ems_not_linked"),
        "rows": rows_out,
        "warnings": [],
    }


def order_has_ems_return_marker(db: Session, order_id: int) -> bool:
    """Đơn có ít nhất một vận đơn EMS với trạng thái hoàn (EMS hoặc shop đã xác nhận)."""
    records = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.order_id == order_id)
        .all()
    )
    if not records:
        return False
    return any(
        _is_ems_return_pending_shop(ems_status=r.ems_status)
        or _is_shop_return_received(order_status=r.order_status)
        for r in records
    )


def validate_shop_return_confirm(order: Order) -> tuple[str, str] | None:
    """Trả (mã lỗi, thông báo) hoặc None nếu được phép xác nhận."""
    status_val = getattr(order.status, "value", order.status)
    if status_val == OrderStatus.RETURNED.value:
        return "already_returned", "Shop đã xác nhận đã nhận hàng hoàn."
    if status_val == OrderStatus.CANCELLED.value:
        return "not_ready", "Đơn đã hủy — không thể xác nhận hoàn."
    return None


def apply_shop_return_received_on_ems_record(
    db: Session,
    record: EmsShippingRecord,
    *,
    admin_id: int,
    note: str | None = None,
) -> None:
    """Ghi nhận shop đã nhận hoàn trên vận đơn EMS; cập nhật đơn shop nếu có và hợp lệ."""
    if record.order_id:
        order = db.query(Order).filter(Order.id == record.order_id).first()
        if order and validate_shop_return_confirm(order) is None:
            apply_shop_return_received_on_order(db, order, admin_id=admin_id, note=note)
            return
    record.order_status = OrderStatus.RETURNED.value
    record.sync_message = RETURN_SHOP_RECEIVED_LABEL


def apply_shop_return_received_on_order(
    db: Session,
    order: Order,
    *,
    admin_id: int,
    note: str | None = None,
) -> None:
    """Cập nhật đơn + EMS — không commit (dùng trong bulk)."""
    old_status = getattr(order.status, "value", order.status)
    now = datetime.now()
    order.status = OrderStatus.RETURNED.value
    order.returned_at = now
    if note:
        prefix = f"\n[Nhận hàng hoàn {now.strftime('%d/%m/%Y %H:%M')}] "
        order.admin_notes = ((order.admin_notes or "") + prefix + note.strip()).strip()
    order.processed_by = admin_id
    order.updated_at = now

    from app.services.warehouse_stock import sync_warehouse_stock_on_status_change

    sync_warehouse_stock_on_status_change(db, order, old_status, OrderStatus.RETURNED.value)
    affiliate_svc.handle_order_status_change(db, order, old_status, OrderStatus.RETURNED.value)

    ems_records = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.order_id == order.id)
        .all()
    )
    for record in ems_records:
        record.order_status = OrderStatus.RETURNED.value
        record.sync_message = RETURN_SHOP_RECEIVED_LABEL


def bulk_confirm_shop_returns(
    db: Session,
    entries: list[dict[str, Any]],
    *,
    admin_id: int,
    note: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """
    entries: { row_number, raw, order_code? }
    Chỉ xác nhận dòng can_confirm (EMS đã báo hoàn).
    """
    rows_out: list[dict[str, Any]] = []
    seen_codes: dict[str, int] = {}
    to_confirm: list[tuple[dict[str, Any], dict[str, Any]]] = []

    for entry in entries:
        row = evaluate_shop_return_entry(db, entry, seen_codes)
        if row.get("can_confirm") and row.get("ems_record_id"):
            to_confirm.append((entry, row))
            continue
        rows_out.append(row)

    confirmed = 0
    for entry, row in to_confirm:
        record = (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.id == int(row["ems_record_id"]))
            .first()
        )
        if not record:
            rows_out.append({**row, "status": "not_ready", "can_confirm": False, "message": "Không tìm thấy vận đơn EMS."})
            continue
        apply_shop_return_received_on_ems_record(db, record, admin_id=admin_id, note=note)
        confirmed += 1
        code = (row.get("order_code") or record.order_code or "").strip().upper() or None
        snap = _ems_snapshot(record)
        rows_out.append(
            {
                "row_number": int(entry.get("row_number") or 0),
                "raw": str(entry.get("raw") or code or "").strip(),
                "order_code": code,
                "order_id": record.order_id,
                "ems_record_id": record.id,
                "order_status": OrderStatus.RETURNED.value,
                "status": "confirmed",
                "message": RETURN_SHOP_RECEIVED_LABEL,
                "can_confirm": False,
                **snap,
            }
        )

    if confirmed:
        db.commit()
    else:
        db.rollback()

    rows_out.sort(key=lambda r: (int(r.get("row_number") or 0), str(r.get("order_code") or "")))

    error_count = sum(1 for r in rows_out if r["status"] != "confirmed")
    confirmable_count = sum(1 for r in rows_out if r.get("can_confirm"))
    return {
        "ok": True,
        "preview": False,
        "source": source,
        "total_rows": len(entries),
        "confirmed_count": confirmed,
        "confirmable_count": confirmable_count,
        "error_count": error_count,
        "not_found_count": sum(1 for r in rows_out if r["status"] == "not_found"),
        "invalid_code_count": sum(1 for r in rows_out if r["status"] == "invalid_code"),
        "already_returned_count": sum(1 for r in rows_out if r["status"] == "already_returned"),
        "invalid_status_count": sum(1 for r in rows_out if r["status"] == "invalid_status"),
        "duplicate_count": sum(1 for r in rows_out if r["status"] == "duplicate"),
        "ems_not_return_count": sum(1 for r in rows_out if r["status"] == "ems_not_return"),
        "ems_not_linked_count": sum(1 for r in rows_out if r["status"] == "ems_not_linked"),
        "rows": rows_out,
        "warnings": [],
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
        raise ValueError("Không tìm thấy đơn hàng.")

    err = validate_shop_return_confirm(order)
    if err:
        raise ValueError(err[1])

    apply_shop_return_received_on_order(db, order, admin_id=admin_id, note=note)
    db.commit()
    db.refresh(order)
    return order
