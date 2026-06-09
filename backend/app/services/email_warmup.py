from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.birthday_promo import BirthdayPromoEmailLog
from app.models.email_send_management import EmailSendManagement
from app.models.user import User
from app.services.birthday_discount import BIRTHDAY_EMAIL_SEND_DAYS_BEFORE, birthday_campaign_key, get_birthday_discount

DEFAULT_START_LIMIT = 5
DEFAULT_DAILY_INCREMENT = 5
UNLIMITED_QUOTA = 999_999
# Khớp deploy/crontab.188.com.vn.example — cron CMSN chạy lúc 9:00 giờ VN
BIRTHDAY_CRON_HOUR = 9
BIRTHDAY_CRON_MINUTE = 0
BIRTHDAY_CRON_TIMEZONE = "Asia/Ho_Chi_Minh"


def birthday_cron_schedule_label() -> str:
    hour = BIRTHDAY_CRON_HOUR
    minute = BIRTHDAY_CRON_MINUTE
    period = "sáng" if hour < 12 else ("trưa" if hour == 12 else "chiều" if hour < 18 else "tối")
    return f"{hour}:{minute:02d} {period} (giờ Việt Nam)"


def get_or_create_management(db: Session) -> EmailSendManagement:
    row = db.query(EmailSendManagement).filter(EmailSendManagement.id == 1).first()
    if row:
        return row
    row = EmailSendManagement(
        id=1,
        warmup_enabled=True,
        start_limit=DEFAULT_START_LIMIT,
        daily_increment=DEFAULT_DAILY_INCREMENT,
        birthday_cron_enabled=True,
        warmup_day=1,
        daily_sent_total=0,
        daily_birthday_sent=0,
        daily_marketing_sent=0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ensure_daily_reset(db: Session, row: EmailSendManagement) -> None:
    today = date.today()
    if row.last_reset_date == today:
        return
    if row.last_reset_date is not None:
        row.warmup_day = max(1, (row.warmup_day or 1) + 1)
    elif row.warmup_started_at is None:
        row.warmup_started_at = datetime.now(timezone.utc)
    row.daily_sent_total = 0
    row.daily_birthday_sent = 0
    row.daily_marketing_sent = 0
    row.last_reset_date = today
    db.commit()


def compute_daily_limit(row: EmailSendManagement) -> int:
    if not row.warmup_enabled:
        return UNLIMITED_QUOTA
    start = max(1, int(row.start_limit or DEFAULT_START_LIMIT))
    increment = max(1, int(row.daily_increment or DEFAULT_DAILY_INCREMENT))
    day = max(1, int(row.warmup_day or 1))
    limit = start + (day - 1) * increment
    if row.max_limit and int(row.max_limit) > 0:
        limit = min(limit, int(row.max_limit))
    return limit


def get_remaining_today(row: EmailSendManagement) -> int:
    if not row.warmup_enabled:
        return UNLIMITED_QUOTA
    limit = compute_daily_limit(row)
    sent = int(row.daily_sent_total or 0)
    return max(0, limit - sent)


def can_send_today(db: Session) -> bool:
    row = get_or_create_management(db)
    ensure_daily_reset(db, row)
    db.refresh(row)
    if not row.warmup_enabled:
        return True
    limit = compute_daily_limit(row)
    return int(row.daily_sent_total or 0) < limit


def record_send(db: Session, *, channel: str) -> None:
    row = get_or_create_management(db)
    ensure_daily_reset(db, row)
    db.refresh(row)
    row.daily_sent_total = int(row.daily_sent_total or 0) + 1
    if channel == "birthday":
        row.daily_birthday_sent = int(row.daily_birthday_sent or 0) + 1
    elif channel == "marketing":
        row.daily_marketing_sent = int(row.daily_marketing_sent or 0) + 1
    db.commit()


def try_consume_send_slot(db: Session, *, channel: str) -> bool:
    if not can_send_today(db):
        return False
    record_send(db, channel=channel)
    return True


def count_birthday_pending(db: Session) -> int:
    today = date.today()
    pending = 0
    users = (
        db.query(User)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.email.isnot(None))
        .filter(User.email != "")
        .filter(User.date_of_birth.isnot(None))
        .all()
    )
    for user in users:
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
        if not exists:
            pending += 1
    return pending


def get_birthday_send_history(db: Session, *, days: int = 14) -> list[dict]:
    since = date.today().toordinal() - max(1, days) + 1
    since_date = date.fromordinal(since)
    rows = (
        db.query(func.date(BirthdayPromoEmailLog.sent_at).label("day"), func.count().label("cnt"))
        .filter(func.date(BirthdayPromoEmailLog.sent_at) >= since_date)
        .group_by(func.date(BirthdayPromoEmailLog.sent_at))
        .order_by(func.date(BirthdayPromoEmailLog.sent_at).desc())
        .all()
    )
    return [{"date": str(r.day), "birthday_sent": int(r.cnt)} for r in rows]


def get_recent_birthday_sent_logs(db: Session, *, days: int = 14, limit: int = 100) -> list[dict]:
    since = date.today().toordinal() - max(1, days) + 1
    since_date = date.fromordinal(since)
    rows = (
        db.query(BirthdayPromoEmailLog, User.full_name)
        .outerjoin(User, User.id == BirthdayPromoEmailLog.user_id)
        .filter(func.date(BirthdayPromoEmailLog.sent_at) >= since_date)
        .order_by(BirthdayPromoEmailLog.sent_at.desc())
        .limit(max(1, min(limit, 500)))
        .all()
    )
    out: list[dict] = []
    for log, full_name in rows:
        sent_at = log.sent_at
        out.append(
            {
                "id": int(log.id),
                "sent_at": sent_at.isoformat() if sent_at else "",
                "recipient_email": log.recipient_email or "",
                "user_id": int(log.user_id),
                "user_name": (full_name or "").strip() or None,
                "birthday_date": log.birthday_date.isoformat() if log.birthday_date else "",
                "campaign_key": log.campaign_key or "",
            }
        )
    return out


def management_payload(db: Session) -> dict:
    row = get_or_create_management(db)
    ensure_daily_reset(db, row)
    db.refresh(row)
    daily_limit = compute_daily_limit(row)
    remaining = get_remaining_today(row)
    total_birthday = db.query(func.count(BirthdayPromoEmailLog.id)).scalar() or 0
    return {
        "warmup_enabled": bool(row.warmup_enabled),
        "start_limit": int(row.start_limit or DEFAULT_START_LIMIT),
        "daily_increment": int(row.daily_increment or DEFAULT_DAILY_INCREMENT),
        "max_limit": int(row.max_limit) if row.max_limit else None,
        "birthday_cron_enabled": bool(row.birthday_cron_enabled),
        "warmup_day": int(row.warmup_day or 1),
        "warmup_started_at": row.warmup_started_at.isoformat() if row.warmup_started_at else None,
        "daily_limit": daily_limit if row.warmup_enabled else None,
        "daily_sent_total": int(row.daily_sent_total or 0),
        "daily_birthday_sent": int(row.daily_birthday_sent or 0),
        "daily_marketing_sent": int(row.daily_marketing_sent or 0),
        "remaining_today": remaining if row.warmup_enabled else None,
        "birthday_pending_today": count_birthday_pending(db),
        "birthday_sent_all_time": int(total_birthday),
        "birthday_send_days_before": BIRTHDAY_EMAIL_SEND_DAYS_BEFORE,
        "birthday_cron_hour": BIRTHDAY_CRON_HOUR,
        "birthday_cron_minute": BIRTHDAY_CRON_MINUTE,
        "birthday_cron_timezone": BIRTHDAY_CRON_TIMEZONE,
        "birthday_cron_schedule_label": birthday_cron_schedule_label(),
        "recent_days": get_birthday_send_history(db, days=14),
        "recent_sent": get_recent_birthday_sent_logs(db, days=14, limit=100),
    }
