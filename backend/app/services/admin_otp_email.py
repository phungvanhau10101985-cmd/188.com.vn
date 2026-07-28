"""Email nhận OTP cho tài khoản quản trị."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.services.linked_admin_staff import display_email_for_admin


def resolve_admin_otp_recipient_email(db: Session, admin: AdminUser) -> str:
    """Email nhận OTP — ưu tiên email đăng nhập shop khi admin có linked_user_id."""
    return display_email_for_admin(db, admin)


def mask_email_for_display(email: str) -> str:
    raw = (email or "").strip()
    if "@" not in raw:
        return raw
    local, domain = raw.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    elif len(local) == 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"
