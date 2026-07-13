"""Token + suppression cho email marketing (ngừng nhận tin)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import marketing_email as crud_marketing_email
from app.crud import newsletter as crud_newsletter

logger = logging.getLogger(__name__)


def _secret() -> bytes:
    return (settings.SECRET_KEY or "dev").encode("utf-8")


def normalize_marketing_email(email: str) -> str:
    return crud_marketing_email.normalize_email(email)


def build_unsubscribe_token(email: str) -> str:
    norm = normalize_marketing_email(email)
    payload = base64.urlsafe_b64encode(norm.encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(_secret(), norm.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def parse_unsubscribe_token(token: str) -> Optional[str]:
    raw = (token or "").strip()
    if "." not in raw:
        return None
    payload_b64, sig = raw.rsplit(".", 1)
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        email = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    norm = normalize_marketing_email(email)
    if "@" not in norm:
        return None
    expected = hmac.new(_secret(), norm.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    return norm


def build_unsubscribe_page_url(email: str) -> str:
    fe = (settings.FRONTEND_BASE_URL or settings.WEBSITE_URL or "").strip().rstrip("/")
    origin = fe or "https://188.com.vn"
    token = build_unsubscribe_token(email)
    return f"{origin}/email/ngung-nhan-tin?token={token}"


def is_marketing_email_suppressed(email: str) -> bool:
    norm = normalize_marketing_email(email)
    if not norm or "@" not in norm:
        return True
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        return crud_marketing_email.is_suppressed(db, norm)
    finally:
        db.close()


def unsubscribe_marketing_email(
    db: Session,
    email: str,
    *,
    source: str = "unsubscribe_link",
) -> tuple[bool, str]:
    """
    Ghi suppression + tắt newsletter nếu có.
    Trả (created_or_updated, masked_email).
    """
    norm = normalize_marketing_email(email)
    if not norm or "@" not in norm:
        raise ValueError("Email không hợp lệ")

    already = crud_marketing_email.is_suppressed(db, norm)
    crud_marketing_email.suppress_email(db, norm, source=source)
    try:
        crud_newsletter.unsubscribe_email(db, norm)
    except Exception:
        logger.exception("newsletter unsubscribe sync failed email=%s", norm)

    masked = crud_marketing_email.mask_email(norm)
    return (not already, masked)
