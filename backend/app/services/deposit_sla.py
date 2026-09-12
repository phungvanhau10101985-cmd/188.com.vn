"""SLA đơn chờ cọc: nhắc khách, đánh dấu quá hạn và nhả giữ tồn VN."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.order import Order, OrderItem, OrderStatus
from app.services.email_service import send_order_email
from app.services.warehouse_stock import release_warehouse_stock_for_order
from app.services import affiliate_wallet as affiliate_svc

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _recipient(order: Order) -> str:
    return (order.customer_email or (order.user.email if order.user else "") or "").strip()


def _send_reminder(order: Order, hours: int) -> bool:
    recipient = _recipient(order)
    if not recipient:
        return False
    code = order.order_code or f"#{order.id}"
    send_order_email(
        recipient,
        f"Nhắc đặt cọc đơn {code} · 188.com.vn",
        (
            f"Đơn {code} đang chờ đặt cọc. Vui lòng hoàn tất chuyển khoản để shop "
            f"xử lý đơn. Đây là lời nhắc sau {hours} giờ; nếu đã chuyển khoản, "
            "bạn có thể bỏ qua email này."
        ),
    )
    return True


def process_deposit_sla(db: Session, *, limit: int = 200) -> dict[str, Any]:
    now = _now()
    reminders = list(settings.DEPOSIT_REMIND_HOURS[:2])
    while len(reminders) < 2:
        reminders.append(20 if len(reminders) else 2)
    first_h, second_h = reminders
    hold_h = settings.VN_STOCK_HOLD_HOURS

    rows = (
        db.query(Order)
        .options(
            selectinload(Order.user),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
        .filter(
            Order.status == OrderStatus.WAITING_DEPOSIT.value,
            or_(
                Order.deposit_reminded_at_2h.is_(None),
                Order.deposit_reminded_at_20h.is_(None),
                and_(
                    Order.fulfillment_source == "vietnam",
                    Order.deposit_hold_overdue.is_(False),
                ),
            ),
        )
        .order_by(Order.created_at.asc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    sent_2h = 0
    sent_20h = 0
    overdue = 0
    released = 0
    cancelled = 0

    for order in rows:
        created = order.created_at
        if not created:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = now - created

        if age >= timedelta(hours=first_h) and not order.deposit_reminded_at_2h:
            try:
                if _send_reminder(order, first_h):
                    sent_2h += 1
                order.deposit_reminded_at_2h = now
            except Exception:
                logger.exception("deposit reminder %sh failed order_id=%s", first_h, order.id)

        if age >= timedelta(hours=second_h) and not order.deposit_reminded_at_20h:
            try:
                if _send_reminder(order, second_h):
                    sent_20h += 1
                order.deposit_reminded_at_20h = now
            except Exception:
                logger.exception("deposit reminder %sh failed order_id=%s", second_h, order.id)

        if (
            (order.fulfillment_source or "").lower() == "vietnam"
            and age >= timedelta(hours=hold_h)
            and not order.deposit_hold_overdue
        ):
            order.deposit_hold_overdue = True
            overdue += 1
            if order.stock_hold_released_at is None:
                release_warehouse_stock_for_order(db, order)
                order.stock_hold_released_at = now
                released += 1
            if settings.AUTO_CANCEL_EXPIRED_DEPOSIT:
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = now
                order.cancelled_reason = "Tự động hủy do quá hạn đặt cọc"
                affiliate_svc.handle_order_status_change(
                    db,
                    order,
                    OrderStatus.WAITING_DEPOSIT.value,
                    OrderStatus.CANCELLED.value,
                )
                cancelled += 1

    db.commit()
    return {
        "ok": True,
        "checked": len(rows),
        "reminded_2h": sent_2h,
        "reminded_20h": sent_20h,
        "overdue": overdue,
        "stock_released": released,
        "cancelled": cancelled,
    }

