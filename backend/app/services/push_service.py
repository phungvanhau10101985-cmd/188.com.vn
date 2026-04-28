# Web Push (VAPID) — thông báo tới PWA/Chrome khi có Notification trong DB
import json
import logging
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.push_subscription import UserPushSubscription
from app.models.notification import Notification

logger = logging.getLogger(__name__)


def is_push_configured() -> bool:
    pub = (getattr(settings, "VAPID_PUBLIC_KEY", None) or "").strip()
    priv = (getattr(settings, "VAPID_PRIVATE_KEY", None) or "").strip()
    return bool(pub and priv)


def send_push_to_user(
    db: Session,
    user_id: int,
    title: str,
    body: str,
    url: str = "/",
    notification_id: Optional[int] = None,
) -> int:
    """
    Gửi web push tới mọi subscription của user. Trả về số gửi thành công.
    Bỏ qua toàn bộ nếu chưa cấu hình VAPID.
    """
    if not is_push_configured():
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush chưa cài, bỏ qua push")
        return 0

    subs: List[UserPushSubscription] = (
        db.query(UserPushSubscription).filter(UserPushSubscription.user_id == user_id).all()
    )
    if not subs:
        return 0

    vapid_priv = (settings.VAPID_PRIVATE_KEY or "").strip().replace("\\n", "\n")
    vapid_sub = (getattr(settings, "VAPID_CLAIM_EMAIL", None) or "mailto:noreply@188.com.vn").strip()
    if not vapid_sub.startswith("mailto:"):
        vapid_sub = f"mailto:{vapid_sub}"

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "notificationId": notification_id,
    }
    data = json.dumps(payload, ensure_ascii=False)
    success = 0
    to_remove: List[UserPushSubscription] = []

    for sub in subs:
        sub_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        try:
            webpush(
                subscription_info=sub_info,
                data=data,
                vapid_private_key=vapid_priv,
                vapid_claims={"sub": vapid_sub},
                ttl=86400,
            )
            success += 1
        except WebPushException as e:
            r = getattr(e, "response", None)
            status = getattr(r, "status_code", None) if r is not None else None
            if status in (404, 410):
                to_remove.append(sub)
                logger.info("Gỡ subscription hết hạn user_id=%s", user_id)
            else:
                logger.warning("WebPush lỗi: %s", e)
        except Exception as e:
            logger.warning("WebPush: %s", e)

    for s in to_remove:
        db.delete(s)
    if to_remove:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return success


def send_for_notification(db: Session, notif: Notification) -> None:
    """Gọi khi tạo thông báo trong app — gửi push tới tài khoản."""
    if not is_push_configured():
        return
    try:
        send_push_to_user(
            db,
            notif.user_id,
            notif.title,
            (notif.content or "")[:500],
            url="/account/notifications",
            notification_id=notif.id,
        )
    except Exception as e:
        logger.debug("push sau notification: %s", e)
