"""Email nhận OTP cho tài khoản quản trị."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.user import User


def resolve_admin_otp_recipient_email(db: Session, admin: AdminUser) -> str:
    """
    Email nhận OTP quản trị (đăng nhập / xóa hàng loạt).

    Khi admin có linked_user_id (vào quản trị qua «Quản trị web»):
    ưu tiên email đăng nhập shop (users.email), không dùng email nội bộ admin_users
    kiểu linked-admin-2@188.com.vn.

    Khi đăng nhập /admin/login trực tiếp (không liên kết user): dùng admin_users.email.
    """
    linked_id = getattr(admin, "linked_user_id", None)
    if linked_id:
        user = db.query(User).filter(User.id == int(linked_id)).first()
        if user:
            user_email = (getattr(user, "email", None) or "").strip()
            if user_email:
                return user_email

    return (getattr(admin, "email", None) or "").strip()


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
