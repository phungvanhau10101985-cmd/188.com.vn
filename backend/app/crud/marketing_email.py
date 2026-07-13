from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.marketing_email_suppression import MarketingEmailSuppression


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_suppressed(db: Session, email: str) -> bool:
    norm = normalize_email(email)
    if not norm or "@" not in norm:
        return True
    row = (
        db.query(MarketingEmailSuppression.id)
        .filter(MarketingEmailSuppression.email == norm)
        .first()
    )
    return row is not None


def suppress_email(
    db: Session,
    email: str,
    *,
    source: str = "unsubscribe_link",
) -> MarketingEmailSuppression:
    norm = normalize_email(email)
    now = _utc_now()
    row = (
        db.query(MarketingEmailSuppression)
        .filter(MarketingEmailSuppression.email == norm)
        .first()
    )
    if row:
        row.source = (source or row.source or "unsubscribe_link")[:50]
        row.unsubscribed_at = now
        db.commit()
        db.refresh(row)
        return row

    row = MarketingEmailSuppression(
        email=norm,
        source=(source or "unsubscribe_link")[:50],
        unsubscribed_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def mask_email(email: str) -> str:
    norm = normalize_email(email)
    if "@" not in norm:
        return "***"
    local, domain = norm.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "***" if local else "***"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"
