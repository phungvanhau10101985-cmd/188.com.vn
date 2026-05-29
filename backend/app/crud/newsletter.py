from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.newsletter_subscriber import NewsletterSubscriber
from app.models.user import User
from app.services.customer_list_import import ParsedCustomerRow

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_subscriber_by_email(db: Session, email: str) -> Optional[NewsletterSubscriber]:
    normalized = (email or "").strip().lower()
    if not normalized:
        return None
    return db.query(NewsletterSubscriber).filter(NewsletterSubscriber.email == normalized).first()


def subscribe_email(
    db: Session,
    *,
    email: str,
    user_id: Optional[int] = None,
    source: str = "footer",
) -> tuple[NewsletterSubscriber, bool]:
    """
    Đăng ký hoặc kích hoạt lại email.
    Trả (row, should_send_welcome).
    """
    normalized = (email or "").strip().lower()
    now = _utc_now()
    existing = get_subscriber_by_email(db, normalized)

    if existing:
        should_welcome = False
        if not existing.is_active:
            existing.is_active = True
            existing.unsubscribed_at = None
            existing.subscribed_at = now
            existing.source = (source or existing.source or "footer")[:50]
            if user_id and not existing.user_id:
                existing.user_id = user_id
            should_welcome = True
        elif user_id and not existing.user_id:
            existing.user_id = user_id
        db.commit()
        db.refresh(existing)
        return existing, should_welcome

    row = NewsletterSubscriber(
        email=normalized,
        user_id=user_id,
        source=(source or "footer")[:50],
        is_active=True,
        subscribed_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)


def list_subscribers(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    q: Optional[str] = None,
    active_only: Optional[bool] = None,
) -> Tuple[List[NewsletterSubscriber], int, int]:
    """Trả (rows, total_filtered, active_total_all)."""
    base = db.query(NewsletterSubscriber)
    active_total = int(
        db.query(func.count(NewsletterSubscriber.id))
        .filter(NewsletterSubscriber.is_active.is_(True))
        .scalar()
        or 0
    )

    if active_only is True:
        base = base.filter(NewsletterSubscriber.is_active.is_(True))
    elif active_only is False:
        base = base.filter(NewsletterSubscriber.is_active.is_(False))

    term = (q or "").strip().lower()
    if term:
        like = f"%{term}%"
        base = base.outerjoin(NewsletterSubscriber.user).filter(
            or_(
                NewsletterSubscriber.email.ilike(like),
                NewsletterSubscriber.source.ilike(like),
                NewsletterSubscriber.subscriber_name.ilike(like),
                NewsletterSubscriber.phone.ilike(like),
            )
        )

    total = int(base.count())
    rows = (
        base.options(joinedload(NewsletterSubscriber.user))
        .order_by(NewsletterSubscriber.subscribed_at.desc(), NewsletterSubscriber.id.desc())
        .offset(max(0, skip))
        .limit(min(max(1, limit), 500))
        .all()
    )
    return rows, total, active_total


def subscriber_to_admin_dict(row: NewsletterSubscriber) -> dict:
    user = getattr(row, "user", None)
    birthday = getattr(row, "birthday", None)
    return {
        "id": row.id,
        "email": row.email,
        "user_id": row.user_id,
        "user_full_name": (getattr(user, "full_name", None) or None) if user else None,
        "subscriber_name": getattr(row, "subscriber_name", None) or None,
        "gender": getattr(row, "gender", None) or None,
        "birthday": birthday.isoformat() if birthday else None,
        "phone": getattr(row, "phone", None) or None,
        "email_original": getattr(row, "email_original", None) or None,
        "source": row.source or "footer",
        "is_active": bool(row.is_active),
        "subscribed_at": _iso(row.subscribed_at),
        "unsubscribed_at": _iso(row.unsubscribed_at),
        "created_at": _iso(row.created_at),
    }


def _apply_profile_fields(
    row: NewsletterSubscriber,
    *,
    name: Optional[str],
    gender: Optional[str],
    birthday: Optional[date],
    phone: Optional[str],
    email_original: Optional[str],
) -> None:
    if name:
        row.subscriber_name = name[:255]
    if gender:
        row.gender = gender[:20]
    if birthday:
        row.birthday = birthday
    if phone:
        row.phone = phone[:20]
    if email_original and email_original.strip().lower() != (row.email or "").lower():
        row.email_original = email_original.strip()[:255]


def _link_user_id_for_email(db: Session, email: str) -> Optional[int]:
    row = (
        db.query(User.id)
        .filter(func.lower(User.email) == email)
        .first()
    )
    return int(row[0]) if row else None


def import_subscribers_bulk(
    db: Session,
    rows: List[ParsedCustomerRow],
    *,
    source: str = "import",
) -> Dict[str, int]:
    """Import khách có profile — không gửi welcome mail."""
    created = 0
    reactivated = 0
    skipped_active = 0
    updated_profile = 0
    now = _utc_now()
    src = (source or "import")[:50]

    for item in rows:
        normalized = (item.email or "").strip().lower()
        if not normalized:
            continue

        existing = get_subscriber_by_email(db, normalized)
        user_id = _link_user_id_for_email(db, normalized)

        if existing:
            if existing.is_active:
                skipped_active += 1
                if user_id and not existing.user_id:
                    existing.user_id = user_id
            else:
                existing.is_active = True
                existing.unsubscribed_at = None
                existing.subscribed_at = now
                existing.source = src
                if user_id:
                    existing.user_id = user_id
                reactivated += 1
            before_name = existing.subscriber_name
            _apply_profile_fields(
                existing,
                name=item.name,
                gender=item.gender,
                birthday=item.birthday,
                phone=item.phone,
                email_original=item.email_original if item.email_corrected else None,
            )
            if (
                item.name
                or item.gender
                or item.birthday
                or item.phone
                or item.email_corrected
            ) and (
                existing.subscriber_name != before_name
                or item.gender
                or item.birthday
                or item.phone
                or item.email_corrected
            ):
                updated_profile += 1
            continue

        db.add(
            NewsletterSubscriber(
                email=normalized,
                user_id=user_id,
                source=src,
                is_active=True,
                subscribed_at=now,
                subscriber_name=(item.name or None),
                gender=(item.gender or None),
                birthday=item.birthday,
                phone=(item.phone or None),
                email_original=(
                    (item.email_original or None)
                    if item.email_corrected
                    else None
                ),
            )
        )
        created += 1

    db.commit()
    return {
        "created": created,
        "reactivated": reactivated,
        "skipped_active": skipped_active,
        "updated_profile": updated_profile,
        "invalid": 0,
        "total_input": len(rows),
    }

def import_emails_bulk(
    db: Session,
    emails: List[str],
    *,
    source: str = "import",
) -> Dict[str, int]:
    """Import chỉ email — tương thích luồng cũ."""
    from app.services.customer_list_import import ParsedCustomerRow

    rows = [
        ParsedCustomerRow(row_number=i + 1, email=e, email_original=e)
        for i, e in enumerate(emails)
        if e
    ]
    result = import_subscribers_bulk(db, rows, source=source)
    return {
        "created": result["created"],
        "reactivated": result["reactivated"],
        "skipped_active": result["skipped_active"],
        "invalid": 0,
        "total_input": len(emails),
    }


def count_active_subscribers(db: Session) -> int:
    return int(
        db.query(func.count(NewsletterSubscriber.id))
        .filter(NewsletterSubscriber.is_active.is_(True))
        .scalar()
        or 0
    )


def iter_active_subscriber_emails(db: Session, *, batch_size: int = 200):
    """Yield email active theo lô."""
    last_id = 0
    while True:
        rows = (
            db.query(NewsletterSubscriber.id, NewsletterSubscriber.email)
            .filter(
                NewsletterSubscriber.is_active.is_(True),
                NewsletterSubscriber.id > last_id,
            )
            .order_by(NewsletterSubscriber.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        for row_id, email in rows:
            last_id = row_id
            if email:
                yield str(email).strip().lower()
