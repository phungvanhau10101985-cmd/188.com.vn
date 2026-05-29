from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.birthday_promo import BirthdayPromoEmailLog
from app.models.user import User
from app.services.birthday_discount import (
    BIRTHDAY_EMAIL_SEND_DAYS_BEFORE,
    birthday_campaign_key,
    get_birthday_discount,
)
from app.services.email_service import send_birthday_promo_email
from app.services.email_warmup import can_send_today, get_or_create_management, record_send


def run_birthday_promo_email_batch(db: Session, *, force: bool = False) -> dict:
    """Gửi email CMSN đúng 7 ngày trước sinh nhật (tôn trọng warm-up quota)."""
    mgmt = get_or_create_management(db)
    if not force and not mgmt.birthday_cron_enabled:
        return {
            "ok": True,
            "skipped_cron_disabled": True,
            "checked": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "deferred_quota": 0,
            "failures": [],
        }

    today = date.today()
    users = (
        db.query(User)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.email.isnot(None))
        .filter(User.email != "")
        .filter(User.date_of_birth.isnot(None))
        .all()
    )

    checked = sent = skipped = failed = deferred_quota = 0
    failures: list[dict[str, str]] = []

    for user in users:
        checked += 1
        promo = get_birthday_discount(user.date_of_birth, today=today)
        if promo.days_until != BIRTHDAY_EMAIL_SEND_DAYS_BEFORE or not promo.next_birthday:
            continue

        campaign_key = birthday_campaign_key(promo.next_birthday)
        exists = (
            db.query(BirthdayPromoEmailLog)
            .filter(
                BirthdayPromoEmailLog.user_id == user.id,
                BirthdayPromoEmailLog.campaign_key == campaign_key,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        if not can_send_today(db):
            deferred_quota += 1
            continue

        email = (user.email or "").strip()
        try:
            send_birthday_promo_email(
                email,
                user.full_name or "",
                promo.percent,
                promo.next_birthday.isoformat(),
                settings.FRONTEND_BASE_URL,
            )
            db.add(
                BirthdayPromoEmailLog(
                    user_id=user.id,
                    campaign_key=campaign_key,
                    birthday_date=promo.next_birthday,
                    recipient_email=email,
                )
            )
            db.commit()
            record_send(db, channel="birthday")
            sent += 1
        except Exception as exc:
            db.rollback()
            failed += 1
            failures.append({"user_id": str(user.id), "error": str(exc)})

    return {
        "ok": failed == 0,
        "checked": checked,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "deferred_quota": deferred_quota,
        "failures": failures[:20],
    }
