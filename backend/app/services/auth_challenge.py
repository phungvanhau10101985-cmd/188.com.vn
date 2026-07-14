"""Reusable, database-backed OTP challenges for recent-auth and admin MFA."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import string
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_challenge import AuthActionChallenge
from app.services.email_service import send_security_otp_email


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_secret(value: str) -> str:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY chưa được cấu hình.")
    pepper = settings.SECRET_KEY.encode("utf-8")
    return hashlib.sha256(pepper + b":" + value.strip().encode("utf-8")).hexdigest()


def acquire_otp_issue_lock(db: Session, key: str) -> None:
    """Serialize OTP issuance per account across PostgreSQL workers."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
    lock_id = int.from_bytes(digest, byteorder="big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


def issue_challenge(
    db: Session,
    *,
    subject_type: str,
    subject_id: int,
    purpose: str,
    email: str,
    payload_hash: Optional[str] = None,
) -> AuthActionChallenge:
    if not email:
        raise ValueError("Tài khoản chưa có email để nhận OTP.")

    acquire_otp_issue_lock(db, f"{subject_type}:{subject_id}:{purpose}")
    now = utcnow()
    existing = (
        db.query(AuthActionChallenge)
        .filter(
            AuthActionChallenge.subject_type == subject_type,
            AuthActionChallenge.subject_id == subject_id,
            AuthActionChallenge.purpose == purpose,
            AuthActionChallenge.consumed_at.is_(None),
            AuthActionChallenge.expires_at > now,
        )
        .order_by(AuthActionChallenge.id.desc())
        .first()
    )
    if existing:
        created = existing.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds() if created else 0
        if age < int(settings.OTP_RESEND_DELAY_SECONDS):
            wait = int(settings.OTP_RESEND_DELAY_SECONDS - age) + 1
            raise ValueError(f"Vui lòng chờ {wait} giây trước khi gửi lại OTP.")

    sent_today = (
        db.query(AuthActionChallenge)
        .filter(
            AuthActionChallenge.subject_type == subject_type,
            AuthActionChallenge.subject_id == subject_id,
            AuthActionChallenge.created_at >= now - timedelta(days=1),
        )
        .count()
    )
    if sent_today >= int(settings.OTP_DAILY_LIMIT):
        raise ValueError("Đã vượt giới hạn gửi OTP trong 24 giờ.")

    db.query(AuthActionChallenge).filter(
        AuthActionChallenge.subject_type == subject_type,
        AuthActionChallenge.subject_id == subject_id,
        AuthActionChallenge.purpose == purpose,
        AuthActionChallenge.consumed_at.is_(None),
    ).delete(synchronize_session=False)

    otp = "".join(secrets.choice(string.digits) for _ in range(6))
    expires_minutes = int(settings.STEP_UP_OTP_EXPIRE_MINUTES)
    row = AuthActionChallenge(
        public_id=secrets.token_urlsafe(32),
        subject_type=subject_type,
        subject_id=subject_id,
        purpose=purpose,
        otp_hash=hash_secret(otp),
        payload_hash=payload_hash,
        expires_at=utcnow() + timedelta(minutes=expires_minutes),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        send_security_otp_email(email, otp, expires_minutes, purpose)
    except Exception:
        db.delete(row)
        db.commit()
        raise
    return row


def consume_challenge(
    db: Session,
    *,
    challenge_id: str,
    subject_type: str,
    subject_id: int,
    purpose: str,
    otp: str,
) -> AuthActionChallenge:
    row = (
        db.query(AuthActionChallenge)
        .filter(
            AuthActionChallenge.public_id == challenge_id,
            AuthActionChallenge.subject_type == subject_type,
            AuthActionChallenge.subject_id == subject_id,
            AuthActionChallenge.purpose == purpose,
            AuthActionChallenge.consumed_at.is_(None),
            AuthActionChallenge.expires_at > utcnow(),
        )
        .first()
    )
    if not row:
        raise ValueError("Mã OTP không tồn tại hoặc đã hết hạn.")
    if row.attempts >= int(settings.STEP_UP_OTP_MAX_ATTEMPTS):
        raise ValueError("Mã OTP đã bị khóa do nhập sai quá nhiều lần.")
    if not secrets.compare_digest(row.otp_hash, hash_secret(otp)):
        db.query(AuthActionChallenge).filter(
            AuthActionChallenge.id == row.id,
            AuthActionChallenge.consumed_at.is_(None),
        ).update(
            {AuthActionChallenge.attempts: AuthActionChallenge.attempts + 1},
            synchronize_session=False,
        )
        db.commit()
        raise ValueError("Mã OTP không đúng.")
    updated = (
        db.query(AuthActionChallenge)
        .filter(
            AuthActionChallenge.id == row.id,
            AuthActionChallenge.consumed_at.is_(None),
            AuthActionChallenge.expires_at > utcnow(),
            AuthActionChallenge.attempts < int(settings.STEP_UP_OTP_MAX_ATTEMPTS),
        )
        .update({AuthActionChallenge.consumed_at: utcnow()}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise ValueError("Mã OTP đã được sử dụng hoặc hết hạn.")
    db.commit()
    db.refresh(row)
    return row
