"""Thông báo khách khi tra EMS có cập nhật trạng thái vận chuyển."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.crud import notification as crud_notification
from app.db.session import SessionLocal
from app.models.order import Order, OrderStatus
from app.models.order_shipment import EmsShippingRecord
from app.schemas.notification import NotificationCreate
from app.services import email_service
from app.services import push_service

logger = logging.getLogger(__name__)

_PHASE_RANK: dict[str, int] = {
    "unknown": 0,
    "posted": 1,
    "in_transit": 2,
    "out_for_delivery": 3,
    "delivered": 4,
    "cod_collected": 5,
    "cod_settled": 6,
}

_PHASE_LABELS: dict[str, str] = {
    "posted": "EMS đã nhận bưu gửi",
    "in_transit": "Hàng đang vận chuyển",
    "out_for_delivery": "Bưu tá đang giao hàng",
    "delivered": "Đã giao hàng thành công",
    "cod_collected": "EMS đã thu tiền COD",
    "cod_settled": "EMS đã hoàn tất COD",
}


@dataclass(frozen=True)
class _NotifyEvent:
    priority: int
    event_key: str
    title: str
    content: str


def _enabled() -> bool:
    return getattr(settings, "EMS_SHIPPING_NOTIFY_ENABLED", True)


def _norm_phase(value: Any) -> str:
    return str(value or "").strip().lower() or "unknown"


def _norm_status(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value).strip().lower()


def snapshot_from_record(db: Session, record: EmsShippingRecord) -> dict[str, Any]:
    order_status = ""
    if record.order_id:
        order = db.query(Order).filter(Order.id == record.order_id).first()
        if order:
            order_status = _norm_status(order.status)
    return {
        "order_id": record.order_id,
        "order_code": (record.order_code or "").strip().upper(),
        "order_status": order_status,
        "ems_phase": _norm_phase(record.ems_phase),
        "ems_status": (record.ems_status or "").strip(),
        "ems_tracking_code": (record.ems_tracking_code or "").strip().upper(),
    }


def snapshot_from_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": result.get("order_id"),
        "order_code": (result.get("order_code") or "").strip().upper(),
        "order_status": _norm_status(result.get("order_status")),
        "ems_phase": _norm_phase(result.get("ems_phase")),
        "ems_status": (result.get("ems_status") or "").strip(),
        "ems_tracking_code": (result.get("ems_tracking_code") or "").strip().upper(),
    }


def _detail_url(order_id: int) -> str:
    fe = (settings.FRONTEND_BASE_URL or "").strip().rstrip("/")
    return f"{fe}/account/orders/{order_id}/tracking" if fe else ""


def _resolve_notification(before: dict[str, Any], after: dict[str, Any]) -> Optional[_NotifyEvent]:
    order_id = after.get("order_id") or before.get("order_id")
    if not order_id:
        return None

    code = after.get("order_code") or before.get("order_code") or f"#{order_id}"
    tracking = after.get("ems_tracking_code") or ""
    ems_detail = (after.get("ems_status") or "").strip()
    before_phase = _norm_phase(before.get("ems_phase"))
    after_phase = _norm_phase(after.get("ems_phase"))
    before_rank = _PHASE_RANK.get(before_phase, 0)
    after_rank = _PHASE_RANK.get(after_phase, 0)

    before_status = _norm_status(before.get("order_status"))
    after_status = _norm_status(after.get("order_status"))
    before_tracking = (before.get("ems_tracking_code") or "").strip().upper()

    candidates: list[_NotifyEvent] = []

    if tracking and not before_tracking:
        tracking_hint = f" Mã vận đơn: {tracking}."
        candidates.append(
            _NotifyEvent(
                priority=20,
                event_key="tracking_assigned",
                title="Cập nhật vận chuyển",
                content=f"Đơn {code} đã có mã vận đơn EMS.{tracking_hint}",
            )
        )

    if after_rank > before_rank and after_phase in _PHASE_LABELS:
        label = _PHASE_LABELS[after_phase]
        detail = f" {ems_detail}" if ems_detail else ""
        candidates.append(
            _NotifyEvent(
                priority=40 + after_rank,
                event_key=f"phase_{after_phase}",
                title=label,
                content=f"Đơn {code}: {label}.{detail}".strip(),
            )
        )

    if (
        after_status == OrderStatus.SHIPPING.value
        and before_status != OrderStatus.SHIPPING.value
        and after_status not in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value)
    ):
        candidates.append(
            _NotifyEvent(
                priority=35,
                event_key="order_shipping",
                title="Đơn đang giao hàng",
                content=f"Đơn {code} đã chuyển sang trạng thái đang giao hàng."
                + (f" Mã EMS: {tracking}." if tracking else ""),
            )
        )

    if after_status in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value) and before_status not in (
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
    ):
        candidates.append(
            _NotifyEvent(
                priority=90,
                event_key="order_delivered",
                title="Đã giao hàng thành công",
                content=f"Đơn {code} đã được giao thành công. Bạn có thể xác nhận đã nhận hàng trên trang đơn hàng.",
            )
        )

    if not candidates:
        return None
    return max(candidates, key=lambda item: item.priority)


def maybe_notify_customer_after_ems_refresh(
    db: Session,
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> bool:
    """Tạo thông báo in-app (+ push) ngay; email gửi nền."""
    if not _enabled():
        return False

    event = _resolve_notification(before, after)
    if not event:
        return False

    order_id = int(after.get("order_id") or before.get("order_id") or 0)
    if order_id <= 0:
        return False

    order = (
        db.query(Order)
        .options(joinloaded(Order.user))
        .filter(Order.id == order_id)
        .first()
    )
    if not order or not order.user_id:
        return False

    try:
        notif = crud_notification.create_notification(
            db,
            NotificationCreate(
                user_id=order.user_id,
                title=event.title,
                content=event.content,
                type="order",
            ),
        )
        tracking_url = f"/account/orders/{order_id}/tracking"
        try:
            push_service.send_push_to_user(
                db,
                order.user_id,
                event.title,
                event.content[:500],
                url=tracking_url,
                notification_id=notif.id,
            )
        except Exception:
            logger.debug("ems_shipment push failed order_id=%s", order_id, exc_info=True)
        db.flush()
    except Exception:
        logger.exception("ems_shipment in-app notify failed order_id=%s event=%s", order_id, event.event_key)
        return False

    send_ems_status_notification_email_task(order_id, event.title, event.content)
    logger.info(
        "ems_shipment notify order_id=%s user_id=%s event=%s",
        order_id,
        order.user_id,
        event.event_key,
    )
    return True


def send_ems_status_notification_email_task(order_id: int, title: str, content: str) -> None:
    threading.Thread(
        target=_send_ems_status_email,
        args=(order_id, title, content),
        name=f"ems-notify-email-{order_id}",
        daemon=True,
    ).start()


def _send_ems_status_email(order_id: int, title: str, content: str) -> None:
    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinloaded(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order:
            return

        customer_to = (order.customer_email or "").strip()
        if not customer_to and order.user and order.user.email:
            customer_to = (order.user.email or "").strip()
        if not customer_to or not settings.is_smtp_configured():
            return

        code = (order.order_code or "").strip() or f"#{order.id}"
        detail_url = _detail_url(order.id)
        subject = title
        if settings.EMAIL_SUBJECT_PREFIX:
            subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

        lines = [content, "", f"Mã đơn: {code}"]
        if detail_url:
            lines.extend(["", f"Theo dõi đơn: {detail_url}"])
        text_body = "\n".join(lines)

        html_parts = [f"<p>{content}</p>", f"<p>Mã đơn: <strong>{code}</strong></p>"]
        if detail_url:
            html_parts.append(f'<p><a href="{detail_url}">Xem hành trình vận chuyển</a></p>')
        html_body = "".join(html_parts)

        email_service.send_email(customer_to, subject, text_body, html_body)
        logger.info("ems_shipment email sent order_id=%s to=%s", order_id, customer_to)
    except Exception:
        logger.exception("ems_shipment email failed order_id=%s", order_id)
    finally:
        db.close()
