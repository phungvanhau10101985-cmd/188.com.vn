"""Nhắc email đánh giá: đơn đã giao 3–7 ngày, còn sản phẩm khách chưa review."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.crud import product_review as crud_product_review
from app.models.order import Order, OrderStatus
from app.services.email_service import send_order_review_reminder_email

logger = logging.getLogger(__name__)

_SCHEDULER_STARTED = False
_SCHEDULER_THREAD: Optional[threading.Thread] = None
_SCHEDULER_LOCK = threading.Lock()


def _enabled() -> bool:
    return bool(getattr(settings, "REVIEW_REMINDER_ENABLED", True))


def _min_days() -> int:
    return max(1, int(getattr(settings, "REVIEW_REMINDER_MIN_DAYS", 3) or 3))


def _max_days() -> int:
    return max(_min_days(), int(getattr(settings, "REVIEW_REMINDER_MAX_DAYS", 7) or 7))


def _batch_size() -> int:
    return max(1, int(getattr(settings, "REVIEW_REMINDER_BATCH_SIZE", 40) or 40))


def _to_aware_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def delivered_in_reminder_window(
    delivered_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    min_days: Optional[int] = None,
    max_days: Optional[int] = None,
) -> bool:
    """True khi đã giao đủ min_days và chưa quá max_days."""
    delivered = _to_aware_utc(delivered_at)
    if delivered is None:
        return False
    current = _to_aware_utc(now) or datetime.now(timezone.utc)
    age = current - delivered
    lo = timedelta(days=min_days if min_days is not None else _min_days())
    hi = timedelta(days=max_days if max_days is not None else _max_days())
    return lo <= age <= hi


def _customer_email(order: Order) -> str:
    email = (order.customer_email or "").strip()
    if email:
        return email
    user = getattr(order, "user", None)
    if user is not None:
        return (getattr(user, "email", None) or "").strip()
    return ""


def _product_ids(order: Order) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for item in order.items or []:
        pid = getattr(item, "product_id", None)
        if pid is None:
            continue
        pid_int = int(pid)
        if pid_int in seen:
            continue
        seen.add(pid_int)
        ids.append(pid_int)
    return ids


def _product_names(order: Order) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in order.items or []:
        name = (getattr(item, "product_name", None) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def order_has_unreviewed_products(db: Session, order: Order) -> bool:
    if not order.user_id:
        return False
    product_ids = _product_ids(order)
    if not product_ids:
        return False
    reviewed = crud_product_review.get_user_reviewed_product_ids(
        db, int(order.user_id), product_ids
    )
    return any(pid not in reviewed for pid in product_ids)


def _candidate_orders(db: Session, *, now: datetime, limit: int) -> list[Order]:
    min_d = _min_days()
    max_d = _max_days()
    # Cửa sổ SQL nới lỏng; delivered_at trên DB thường naive (datetime.now() lúc giao).
    naive_now = now.replace(tzinfo=None) if now.tzinfo else now
    window_start = naive_now - timedelta(days=max_d + 1)
    window_end = naive_now - timedelta(days=max(0, min_d - 1))
    return (
        db.query(Order)
        .options(joinedload(Order.items), joinedload(Order.user))
        .filter(
            Order.status.in_(
                [OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value]
            )
        )
        .filter(Order.delivered_at.isnot(None))
        .filter(Order.review_reminder_sent_at.is_(None))
        .filter(Order.user_id.isnot(None))
        .filter(Order.delivered_at >= window_start)
        .filter(Order.delivered_at <= window_end)
        .order_by(Order.delivered_at.asc())
        .limit(max(limit * 4, 80))
        .all()
    )


def run_review_reminder_batch(
    db: Session,
    *,
    now: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    """Gửi tối đa `limit` mail nhắc; mỗi đơn một lần. Tôn trọng REVIEW_REMINDER_ENABLED."""
    if not _enabled():
        return {
            "ok": True,
            "skipped_disabled": True,
            "checked": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
        }

    current = _to_aware_utc(now) or datetime.now(timezone.utc)
    cap = limit if limit is not None else _batch_size()
    min_d = _min_days()
    max_d = _max_days()

    checked = sent = skipped = failed = 0
    sent_ids: list[int] = []
    failures: list[dict[str, str]] = []

    for order in _candidate_orders(db, now=current, limit=cap):
        if sent >= cap:
            break
        checked += 1
        if not delivered_in_reminder_window(
            order.delivered_at, now=current, min_days=min_d, max_days=max_d
        ):
            skipped += 1
            continue
        if getattr(order, "review_reminder_sent_at", None):
            skipped += 1
            continue
        if not order_has_unreviewed_products(db, order):
            skipped += 1
            continue
        to_email = _customer_email(order)
        if not to_email:
            skipped += 1
            continue
        try:
            ok = send_order_review_reminder_email(
                to_email=to_email,
                customer_name=order.customer_name or "",
                order_code=order.order_code or "",
                order_id=int(order.id),
                product_names=_product_names(order),
            )
            if not ok:
                skipped += 1
                logger.info(
                    "review_reminder skip send=false order_id=%s", order.id
                )
                continue
            order.review_reminder_sent_at = datetime.now(timezone.utc)
            db.commit()
            sent += 1
            sent_ids.append(int(order.id))
        except Exception as exc:
            db.rollback()
            failed += 1
            failures.append({"order_id": str(order.id), "error": str(exc)[:200]})
            logger.exception("review_reminder failed order_id=%s", order.id)

    logger.info(
        "review_reminder batch checked=%s sent=%s skipped=%s failed=%s",
        checked,
        sent,
        skipped,
        failed,
    )
    return {
        "ok": True,
        "checked": checked,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "sent_order_ids": sent_ids,
        "failures": failures,
        "min_days": min_d,
        "max_days": max_d,
    }


def _scheduler_loop() -> None:
    interval = max(
        1, int(getattr(settings, "REVIEW_REMINDER_INTERNAL_INTERVAL_HOURS", 6) or 6)
    )
    time.sleep(45)
    while True:
        try:
            from app.db.session import SessionLocal

            db = SessionLocal()
            try:
                run_review_reminder_batch(db)
            finally:
                db.close()
        except Exception:
            logger.exception("review_reminder scheduler tick failed")
        time.sleep(interval * 3600)


def start_review_reminder_scheduler_if_enabled() -> None:
    global _SCHEDULER_STARTED, _SCHEDULER_THREAD
    if not _enabled():
        return
    if not getattr(settings, "REVIEW_REMINDER_INTERNAL_SCHEDULER_ENABLED", True):
        return
    with _SCHEDULER_LOCK:
        if _SCHEDULER_STARTED:
            return
        _SCHEDULER_THREAD = threading.Thread(
            target=_scheduler_loop,
            name="review-reminder-scheduler",
            daemon=True,
        )
        _SCHEDULER_THREAD.start()
        _SCHEDULER_STARTED = True
        logger.info(
            "review_reminder internal scheduler started (every %sh)",
            int(getattr(settings, "REVIEW_REMINDER_INTERNAL_INTERVAL_HOURS", 6) or 6),
        )
