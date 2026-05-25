"""Thông báo khách khi shop đóng hàng & gửi shipper — kèm link đơn và nhắc đánh giá sau khi nhận."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.crud import notification as crud_notification
from app.db.session import SessionLocal
from app.models.order import Order
from app.schemas.notification import NotificationCreate
from app.services import email_service
from app.services import push_service

logger = logging.getLogger(__name__)

_REVIEW_HINT = (
    "Sau khi nhận đủ hàng, vui lòng bấm «Đã nhận hàng» trên trang đơn. "
    "Nếu bạn hài lòng, rất mong bạn dành chút thời gian đánh giá — "
    "ý kiến của bạn giúp 188.com.vn nâng cao chất lượng sản phẩm và dịch vụ."
)


def _enabled() -> bool:
    return getattr(settings, "ORDER_SHIPPER_NOTIFY_ENABLED", True)


def schedule_customer_shipper_confirmed_notify(order_id: int) -> None:
    """Gửi thông báo + email nền sau khi shop xác nhận gửi shipper."""
    if not _enabled():
        return

    def _run() -> None:
        # Chờ transaction commit trước khi đọc lại đơn (API / import EMS).
        time.sleep(1.5)
        _notify_customer_shipper_confirmed(order_id)

    threading.Thread(
        target=_run,
        name=f"shipper-notify-{order_id}",
        daemon=True,
    ).start()


def _order_detail_path(order_id: int) -> str:
    return f"/account/orders/{order_id}"


def _notify_customer_shipper_confirmed(order_id: int) -> None:
    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order or not order.user_id:
            return

        code = (order.order_code or "").strip() or f"#{order.id}"
        tracking = (order.tracking_number or "").strip()
        tracking_hint = f" Mã vận đơn: {tracking}." if tracking else ""

        title = "Hàng đang được giao"
        content = (
            f"188.com.vn đã đóng hàng và gửi shipper giao đơn {code} đến bạn.{tracking_hint} "
            f"{_REVIEW_HINT}"
        )

        try:
            notif = crud_notification.create_notification(
                db,
                NotificationCreate(
                    user_id=order.user_id,
                    title=title,
                    content=content,
                    type="order",
                ),
            )
            try:
                push_service.send_push_to_user(
                    db,
                    order.user_id,
                    title,
                    content[:500],
                    url=_order_detail_path(order_id),
                    notification_id=notif.id,
                )
            except Exception:
                logger.debug("shipper_notify push failed order_id=%s", order_id, exc_info=True)
            db.commit()
        except Exception:
            logger.exception("shipper_notify in-app failed order_id=%s", order_id)
            db.rollback()

        email_service.send_order_shipper_confirmed_email_task(order_id)
        logger.info("shipper_notify sent order_id=%s user_id=%s", order_id, order.user_id)
    except Exception:
        logger.exception("shipper_notify failed order_id=%s", order_id)
    finally:
        db.close()


def notify_customer_delivered_with_review(order_id: int, *, source: str = "customer_confirm") -> None:
    """In-app + push: giao hàng thành công + mời đánh giá (không gửi email — email gửi riêng 1 lần)."""
    db = SessionLocal()
    try:
        order = (
            db.query(Order)
            .options(joinedload(Order.user))
            .filter(Order.id == order_id)
            .first()
        )
        if not order or not order.user_id:
            return

        code = (order.order_code or "").strip() or f"#{order.id}"
        if source == "ems_auto":
            title = "Đã giao hàng thành công"
            content = (
                f"Đơn {code} đã được giao thành công. "
                "Nếu hài lòng, mong bạn đánh giá sản phẩm — "
                "ý kiến của bạn giúp 188.com.vn cải thiện dịch vụ."
            )
        else:
            title = "Cảm ơn bạn đã nhận hàng"
            content = (
                f"Đơn {code} đã được xác nhận nhận hàng. "
                "Nếu hài lòng, rất mong bạn đánh giá sản phẩm — "
                "ý kiến của bạn giúp 188.com.vn cải thiện chất lượng và dịch vụ mỗi ngày."
            )
        review_path = f"/account/orders/{order.id}/review"

        try:
            notif = crud_notification.create_notification(
                db,
                NotificationCreate(
                    user_id=order.user_id,
                    title=title,
                    content=content,
                    type="order",
                ),
            )
            try:
                push_service.send_push_to_user(
                    db,
                    order.user_id,
                    title,
                    content[:500],
                    url=review_path,
                    notification_id=notif.id,
                )
            except Exception:
                logger.debug("delivered_review push failed order_id=%s", order.id, exc_info=True)
            db.commit()
        except Exception:
            logger.exception("delivered_review in-app failed order_id=%s", order.id)
            db.rollback()
    except Exception:
        logger.exception("delivered_review notify failed order_id=%s", order_id)
    finally:
        db.close()


def notify_customer_review_after_received(order_id: int) -> None:
    """Alias — giữ tương thích code cũ."""
    notify_customer_delivered_with_review(order_id, source="customer_confirm")
