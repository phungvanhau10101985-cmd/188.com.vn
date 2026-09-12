"""Cảnh báo SLA vận hành chỉ để hiển thị, không tự đổi trạng thái."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_shipment import OrderShipmentEvent

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def business_hours_between(start: datetime, end: datetime) -> float:
    """Số giờ 08:00–18:00, bỏ Chủ Nhật, theo giờ Việt Nam."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    cursor = start.astimezone(VN_TZ)
    finish = end.astimezone(VN_TZ)
    total = 0.0
    day = cursor.date()
    while day <= finish.date():
        if day.weekday() != 6:
            opened = datetime.combine(day, time(8, 0), VN_TZ)
            closed = datetime.combine(day, time(18, 0), VN_TZ)
            left = max(cursor, opened)
            right = min(finish, closed)
            if right > left:
                total += (right - left).total_seconds() / 3600
        day += timedelta(days=1)
    return total


def enrich_admin_orders_sla(db: Session, orders: list[Order]) -> None:
    if not orders:
        return
    now = datetime.now(timezone.utc)
    events = (
        db.query(OrderShipmentEvent)
        .filter(
            OrderShipmentEvent.order_id.in_([order.id for order in orders]),
            OrderShipmentEvent.status == "active",
        )
        .all()
    )
    active_by_order = {event.order_id: event for event in events}

    for order in orders:
        warnings: list[str] = []
        status = getattr(order.status, "value", order.status)
        source = (order.fulfillment_source or "vietnam").strip().lower()
        started = order.confirmed_at or order.created_at
        if source == "vietnam" and started:
            if (
                status == OrderStatus.CONFIRMED.value
                and business_hours_between(started, now) >= 4
            ):
                warnings.append("VN quá 4 giờ làm việc chưa bắt đầu soạn hàng")
            started_utc = (
                started.replace(tzinfo=timezone.utc)
                if started.tzinfo is None
                else started.astimezone(timezone.utc)
            )
            if (
                status in (OrderStatus.CONFIRMED.value, OrderStatus.PROCESSING.value)
                and order.shipped_at is None
                and now - started_utc >= timedelta(hours=24)
            ):
                warnings.append("VN quá 24 giờ chưa bàn giao đơn vị vận chuyển")
        elif source == "china":
            active = active_by_order.get(order.id)
            due = active.scheduled_at if active else None
            if due:
                due_utc = (
                    due.replace(tzinfo=timezone.utc)
                    if due.tzinfo is None
                    else due.astimezone(timezone.utc)
                )
                if due_utc < now:
                    warnings.append(f"TQ quá SLA tại bước {active.step_key}")

        if status == OrderStatus.SHIPPING.value and not (
            order.tracking_number or ""
        ).strip():
            warnings.append("Đang giao nhưng thiếu mã vận đơn")
        order.sla_warnings = warnings

