"""Mã xem trước giao diện lễ, dùng khi admin và cửa hàng là hai host."""

from __future__ import annotations

import hashlib
import hmac
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.holiday_schedule import CATALOG
from app.utils.display_timeline import db_datetime_to_utc

PREVIEW_TTL_SECONDS = 10 * 60


def _secret() -> bytes:
    return (settings.SECRET_KEY or "dev").encode("utf-8")


def issue_holiday_preview_token(code: str, *, now: int | None = None) -> tuple[str, int]:
    theme = (code or "").strip()
    if theme not in CATALOG:
        raise ValueError("Dịp lễ không có trong danh sách")
    issued = int(time.time() if now is None else now)
    expires_at = issued + PREVIEW_TTL_SECONDS
    payload = f"{theme}.{expires_at}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", expires_at


def parse_holiday_preview_token(token: str, *, now: int | None = None) -> tuple[str, int] | None:
    raw = (token or "").strip()
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    code, exp_text, sig = parts
    if code not in CATALOG or not exp_text.isdigit() or len(sig) != 32:
        return None
    payload = f"{code}.{exp_text}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    expires_at = int(exp_text)
    current = int(time.time() if now is None else now)
    if current >= expires_at:
        return None
    return code, expires_at


def shop_user_can_see_admin_preview(admin, user) -> bool:
    """Tài khoản shop gắn với admin (linked user hoặc cùng email) mới thấy bản xem trước."""
    if admin is None or user is None or not getattr(admin, "is_active", False):
        return False
    linked = getattr(admin, "linked_user_id", None)
    user_id = getattr(user, "id", None)
    if linked is not None and user_id is not None and int(linked) == int(user_id):
        return True
    admin_email = (getattr(admin, "email", None) or "").strip().lower()
    user_email = (getattr(user, "email", None) or "").strip().lower()
    return bool(admin_email and admin_email == user_email)


def coerce_preview_expiry(expires_at: datetime | None, *, now: datetime | None = None) -> int | None:
    """Unix giây còn hiệu lực.

    psycopg2 thường trả timestamptz thành datetime naive theo giờ Việt Nam.
    Gắn UTC vào giá trị đó làm bản xem trước 10 phút còn đếm thêm nhiều giờ.
    """
    aware = db_datetime_to_utc(expires_at)
    if aware is None:
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if aware <= current:
        return None
    return int(aware.timestamp())


def _clear_preview_fields(row) -> None:
    row.preview_code = None
    row.preview_admin_id = None
    row.preview_expires_at = None


def live_holiday_preview(db: Session, *, now: datetime | None = None) -> tuple[str, int] | None:
    """Bản xem trước còn hiệu lực. Hết hạn thì xóa khỏi DB để cửa hàng ngừng đếm."""
    from app.crud import holiday_theme as holiday_theme_crud

    row = holiday_theme_crud.get_singleton(db)
    if row is None or not row.preview_code or row.preview_expires_at is None:
        return None
    if row.preview_code not in CATALOG:
        _clear_preview_fields(row)
        db.commit()
        return None
    expires_unix = coerce_preview_expiry(row.preview_expires_at, now=now)
    if expires_unix is None:
        _clear_preview_fields(row)
        db.commit()
        return None
    return row.preview_code, expires_unix


def save_admin_holiday_preview(db: Session, admin, code: str, expires_at: int) -> None:
    from app.crud import holiday_theme as holiday_theme_crud

    row = holiday_theme_crud.get_or_create_singleton(db)
    row.preview_code = code
    row.preview_admin_id = int(admin.id)
    row.preview_expires_at = datetime.fromtimestamp(int(expires_at), tz=timezone.utc)
    db.commit()


def clear_admin_holiday_preview(db: Session, admin) -> None:
    from app.crud import holiday_theme as holiday_theme_crud

    row = holiday_theme_crud.get_singleton(db)
    if row is None or row.preview_admin_id != int(admin.id):
        return
    _clear_preview_fields(row)
    db.commit()


def holiday_preview_for_shop_user(db: Session, user, *, now: datetime | None = None) -> tuple[str, int] | None:
    from app.crud import holiday_theme as holiday_theme_crud
    from app.models.admin import AdminUser

    row = holiday_theme_crud.get_singleton(db)
    if row is None or row.preview_admin_id is None:
        return None
    live = live_holiday_preview(db, now=now)
    if live is None:
        return None
    admin = db.query(AdminUser).filter(AdminUser.id == row.preview_admin_id).first()
    if not shop_user_can_see_admin_preview(admin, user):
        return None
    return live
