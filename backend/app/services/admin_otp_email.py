"""Email nhận OTP cho tài khoản quản trị."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.user import User


def resolve_admin_otp_recipient_email(db: Session, admin: AdminUser) -> str:
    """
    Email nhận OTP quản trị (đăng nhập / xóa hàng loạt).
    Ưu tiên admin_users.email; fallback users.email khi có linked_user_id.
    """
    direct = (getattr(admin, "email", None) or "").strip()
    if direct:
        return direct

    linked_id = getattr(admin, "linked_user_id", None)
    if not linked_id:
        return ""

    user = db.query(User).filter(User.id == int(linked_id)).first()
    if not user:
        return ""
    return (getattr(user, "email", None) or "").strip()


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
