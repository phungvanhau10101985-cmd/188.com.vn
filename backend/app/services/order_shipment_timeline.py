from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.order_shipment import OrderShipmentEvent

logger = logging.getLogger(__name__)

EVENT_PENDING = "pending"
EVENT_ACTIVE = "active"
EVENT_COMPLETED = "completed"
EVENT_SKIPPED = "skipped"

TIMELINE_START_STATUSES = frozenset({
    OrderStatus.DEPOSIT_PAID.value,
    OrderStatus.CONFIRMED.value,
    OrderStatus.PROCESSING.value,
    OrderStatus.SHIPPING.value,
    OrderStatus.DELIVERED.value,
    OrderStatus.COMPLETED.value,
})

FOOTER_NOTE = (
    "188.com.vn trực tiếp vận hành đơn hàng từ Trung Quốc về Việt Nam và luôn ưu tiên xử lý "
    "nhanh nhất có thể. Mọi cập nhật mới sẽ hiển thị ngay tại đây."
)

STEP_CUSTOMER_HINTS: dict[str, str] = {
    "at_customs": (
        "188.com.vn đang chủ động làm thủ tục tại cửa khẩu để chuyển hàng về cho bạn sớm nhất. "
        "Có bước tiếp theo, shop sẽ cập nhật ngay trên lịch trình này."
    ),
    "domestic_shipping": "188.com.vn đã hoàn tất thủ tục — hàng đang được giao tới bạn.",
}


def _step_defs(deposit_flow: bool) -> list[dict[str, Any]]:
    first_title = (
        "Đã đặt cọc — 188.com.vn đã xác nhận đơn"
        if deposit_flow
        else "188.com.vn đã xác nhận đơn hàng"
    )
    return [
        {"key": "deposit_confirmed", "title": first_title, "auto_hours": 0},
        {"key": "tq_preparing", "title": "188.com.vn TQ đang chuẩn bị & đóng gói hàng", "auto_hours": 24},
        {"key": "tq_warehouse", "title": "Hàng đã về kho 188.com.vn TQ", "auto_hours": 24},
        {
            "key": "international_shipping",
            "title": "188.com.vn đang vận chuyển quốc tế (TQ → VN)",
            "auto_hours": 24,
        },
        {
            "key": "at_customs",
            "title": "188.com.vn đang làm thủ tục tại cửa khẩu",
            "auto_hours": 0,
            "pause_here": True,
        },
        {
            "key": "domestic_shipping",
            "title": "188.com.vn đã thông quan — đang giao nội địa tới bạn",
            "manual": True,
        },
        {
            "key": "awaiting_confirm",
            "title": "188.com.vn đã giao — vui lòng xác nhận đã nhận hàng",
            "manual": True,
        },
    ]


def _order_status_value(order: Order) -> str:
    return getattr(order.status, "value", order.status) or ""


def _deposit_flow(order: Order) -> bool:
    paid = float(getattr(order, "deposit_paid", None) or 0)
    if paid > 0:
        return True
    req = getattr(order, "requires_deposit", False)
    st = _order_status_value(order)
    return bool(req) or st == OrderStatus.DEPOSIT_PAID.value


def should_have_timeline(order: Order) -> bool:
    st = _order_status_value(order)
    if st in (OrderStatus.CANCELLED.value, OrderStatus.WAITING_DEPOSIT.value, OrderStatus.PENDING.value):
        return False
    return st in TIMELINE_START_STATUSES


def ensure_shipment_timeline(db: Session, order: Order, *, force: bool = False) -> bool:
    if not should_have_timeline(order):
        return False
    exists = db.query(OrderShipmentEvent.id).filter(OrderShipmentEvent.order_id == order.id).first()
    if exists and not force:
        return False

    if force:
        db.query(OrderShipmentEvent).filter(OrderShipmentEvent.order_id == order.id).delete()

    now = datetime.utcnow()
    steps = _step_defs(_deposit_flow(order))
    for idx, step in enumerate(steps):
        db.add(
            OrderShipmentEvent(
                order_id=order.id,
                step_key=step["key"],
                title=step["title"],
                sort_order=idx,
                status=EVENT_PENDING,
            )
        )
    db.flush()

    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order.id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )
    if not events:
        return False

    first = events[0]
    first.status = EVENT_COMPLETED
    first.completed_at = now

    if len(events) > 1:
        second = events[1]
        second.status = EVENT_ACTIVE
        second.scheduled_at = now + timedelta(hours=steps[1]["auto_hours"])

    _sync_order_processing_status(db, order, events)
    return True


def _activate_next(db: Session, order: Order, events: list[OrderShipmentEvent], current_idx: int) -> None:
    steps = _step_defs(_deposit_flow(order))
    if current_idx + 1 >= len(events):
        return
    nxt = events[current_idx + 1]
    if nxt.status in (EVENT_COMPLETED, EVENT_ACTIVE):
        return
    step_def = steps[current_idx + 1] if current_idx + 1 < len(steps) else {}
    auto_h = int(step_def.get("auto_hours") or 0)
    if step_def.get("pause_here") and auto_h > 0:
        nxt.status = EVENT_PENDING
        nxt.scheduled_at = datetime.utcnow() + timedelta(hours=auto_h)
        return
    if step_def.get("manual") or step_def.get("pause_here"):
        nxt.status = EVENT_ACTIVE
        nxt.scheduled_at = None
        return
    nxt.status = EVENT_ACTIVE
    nxt.scheduled_at = datetime.utcnow() + timedelta(hours=auto_h) if auto_h > 0 else datetime.utcnow()


def _activate_due_pending(events: list[OrderShipmentEvent]) -> int:
    now = datetime.utcnow()
    activated = 0
    for ev in events:
        if ev.status != EVENT_PENDING or not ev.scheduled_at or ev.scheduled_at > now:
            continue
        ev.status = EVENT_ACTIVE
        ev.scheduled_at = None
        activated += 1
    return activated


def advance_auto_milestones(db: Session, order_id: int) -> int:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return 0
    if not db.query(OrderShipmentEvent.id).filter(OrderShipmentEvent.order_id == order_id).first():
        ensure_shipment_timeline(db, order)
        db.flush()

    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order_id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )
    if not events:
        return 0

    advanced = _activate_due_pending(events)

    steps = _step_defs(_deposit_flow(order))
    step_by_key = {s["key"]: s for s in steps}
    now = datetime.utcnow()

    for idx, ev in enumerate(events):
        if ev.status != EVENT_ACTIVE:
            continue
        step_def = step_by_key.get(ev.step_key) or {}
        if step_def.get("manual"):
            continue
        if step_def.get("pause_here"):
            continue
        if ev.scheduled_at and ev.scheduled_at > now:
            continue

        ev.status = EVENT_COMPLETED
        ev.completed_at = now
        advanced += 1
        _activate_next(db, order, events, idx)

    if advanced:
        events = (
            db.query(OrderShipmentEvent)
            .filter(OrderShipmentEvent.order_id == order_id)
            .order_by(OrderShipmentEvent.sort_order.asc())
            .all()
        )
        _sync_order_processing_status(db, order, events)
    return advanced


def advance_auto_milestones_batch(db: Session, limit: int = 200) -> int:
    pending_rows = (
        db.query(OrderShipmentEvent.order_id)
        .filter(OrderShipmentEvent.status == EVENT_PENDING)
        .filter(OrderShipmentEvent.scheduled_at.isnot(None))
        .filter(OrderShipmentEvent.scheduled_at <= datetime.utcnow())
        .distinct()
        .limit(limit)
        .all()
    )
    active_rows = (
        db.query(OrderShipmentEvent.order_id)
        .filter(OrderShipmentEvent.status == EVENT_ACTIVE)
        .filter(OrderShipmentEvent.scheduled_at.isnot(None))
        .filter(OrderShipmentEvent.scheduled_at <= datetime.utcnow())
        .distinct()
        .limit(limit)
        .all()
    )
    order_ids = list({oid for (oid,) in pending_rows + active_rows})
    total = 0
    for order_id in order_ids:
        total += advance_auto_milestones(db, order_id)
    if total:
        db.commit()
    return total


def _sync_order_processing_status(db: Session, order: Order, events: list[OrderShipmentEvent]) -> None:
    st = _order_status_value(order)
    if st in (OrderStatus.CANCELLED.value, OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value, OrderStatus.SHIPPING.value):
        return
    active_keys = {e.step_key for e in events if e.status == EVENT_ACTIVE}
    completed_keys = {e.step_key for e in events if e.status == EVENT_COMPLETED}
    if active_keys & {"at_customs", "international_shipping", "tq_warehouse", "tq_preparing"}:
        if st in (OrderStatus.DEPOSIT_PAID.value, OrderStatus.CONFIRMED.value):
            order.status = OrderStatus.PROCESSING.value
    elif "deposit_confirmed" in completed_keys and st == OrderStatus.CONFIRMED.value:
        order.status = OrderStatus.PROCESSING.value


def admin_clear_customs_and_ship(
    db: Session,
    order_id: int,
    admin_id: int,
    *,
    tracking_number: Optional[str] = None,
    shipping_provider: Optional[str] = None,
) -> Order:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise ValueError("Không tìm thấy đơn hàng.")

    advance_auto_milestones(db, order_id)
    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order_id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )
    customs = next((e for e in events if e.step_key == "at_customs"), None)
    if not customs or customs.status != EVENT_ACTIVE:
        raise ValueError("Đơn chưa ở bước cửa khẩu hoặc đã được xử lý.")

    now = datetime.utcnow()
    customs.status = EVENT_COMPLETED
    customs.completed_at = now
    customs.updated_by_admin_id = admin_id

    domestic = next((e for e in events if e.step_key == "domestic_shipping"), None)
    if domestic:
        domestic.status = EVENT_ACTIVE
        domestic.updated_by_admin_id = admin_id

    if tracking_number:
        order.tracking_number = tracking_number.strip()
    if shipping_provider:
        order.shipping_provider = shipping_provider.strip()

    order.status = OrderStatus.SHIPPING.value
    order.shipped_at = now
    db.flush()
    return order


def mark_delivered_on_timeline(db: Session, order: Order, *, admin_id: Optional[int] = None) -> None:
    if not db.query(OrderShipmentEvent.id).filter(OrderShipmentEvent.order_id == order.id).first():
        ensure_shipment_timeline(db, order)

    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order.id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )
    now = datetime.utcnow()
    for ev in events:
        if ev.step_key == "domestic_shipping" and ev.status == EVENT_ACTIVE:
            ev.status = EVENT_COMPLETED
            ev.completed_at = now
            if admin_id:
                ev.updated_by_admin_id = admin_id
        if ev.step_key == "awaiting_confirm":
            if ev.status == EVENT_PENDING:
                ev.status = EVENT_ACTIVE
            if _order_status_value(order) in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
                ev.status = EVENT_COMPLETED
                ev.completed_at = now


def get_timeline_payload(db: Session, order: Order) -> dict[str, Any]:
    advance_auto_milestones(db, order.id)
    if not db.query(OrderShipmentEvent.id).filter(OrderShipmentEvent.order_id == order.id).first():
        if should_have_timeline(order):
            ensure_shipment_timeline(db, order)
            db.flush()
            advance_auto_milestones(db, order.id)

    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order.id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )

    st = _order_status_value(order)
    if st in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
        mark_delivered_on_timeline(db, order)

    current_key = None
    waiting_admin = False
    for ev in events:
        if ev.status == EVENT_ACTIVE:
            current_key = ev.step_key
            if ev.step_key == "at_customs":
                waiting_admin = True
            break

    step_titles = {s["key"]: s["title"] for s in _step_defs(_deposit_flow(order))}

    return {
        "order_id": order.id,
        "order_code": order.order_code,
        "order_status": st,
        "tracking_number": getattr(order, "tracking_number", None),
        "shipping_provider": getattr(order, "shipping_provider", None),
        "footer_note": FOOTER_NOTE,
        "current_step_key": current_key,
        "waiting_admin_at_customs": waiting_admin,
        "events": [
            {
                "step_key": ev.step_key,
                "title": step_titles.get(ev.step_key, ev.title),
                "status": ev.status,
                "scheduled_at": ev.scheduled_at,
                "completed_at": ev.completed_at,
                "note": ev.note or STEP_CUSTOMER_HINTS.get(ev.step_key),
            }
            for ev in events
        ],
    }


def backfill_timelines(db: Session, limit: int = 500) -> int:
    orders = (
        db.query(Order)
        .filter(
            Order.status.in_(
                [
                    OrderStatus.DEPOSIT_PAID.value,
                    OrderStatus.CONFIRMED.value,
                    OrderStatus.PROCESSING.value,
                    OrderStatus.SHIPPING.value,
                    OrderStatus.DELIVERED.value,
                    OrderStatus.COMPLETED.value,
                ]
            )
        )
        .order_by(Order.id.desc())
        .limit(limit)
        .all()
    )
    created = 0
    for order in orders:
        if ensure_shipment_timeline(db, order):
            created += 1
            advance_auto_milestones(db, order.id)
    if created:
        db.commit()
    return created
