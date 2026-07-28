"""Gán / gỡ quyền quản trị web qua linked_user_id (users ↔ admin_users)."""
from __future__ import annotations

import random
import secrets
import string
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.admin_permissions import normalize_module_list
from app.core.security import get_password_hash
from app.models.admin import AdminUser, AdminRole
from app.models.user import User
from app.services.staff_admin_cleanup import remove_linked_staff_admin_row

LINKABLE_ROLES = frozenset(
    {
        AdminRole.ADMIN,
        AdminRole.ORDER_MANAGER,
        AdminRole.PRODUCT_MANAGER,
        AdminRole.CONTENT_MANAGER,
    }
)


def _random_username(uid: int) -> str:
    suf = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"cust_admin_{uid}_{suf}"


def _resolved_granular(role: AdminRole, modules: Optional[List[str]]) -> Optional[List[str]]:
    """ADMIN luôn full (không lưu granular). modules=None → preset theo role."""
    if role == AdminRole.ADMIN:
        return None
    if modules is None:
        return None
    normalized = normalize_module_list(modules)
    return normalized if normalized else None


def display_email_for_admin(db: Session, admin: AdminUser) -> str:
    """
    Email hiển thị / OTP cho admin liên kết shop (#7 …):
    luôn là email đăng nhập thành viên (users.email), không phải email nội bộ admin_users.
    Admin đăng nhập /admin/login: dùng admin_users.email.
    """
    linked_id = getattr(admin, "linked_user_id", None)
    if linked_id:
        user = db.query(User).filter(User.id == int(linked_id)).first()
        if user:
            user_email = (getattr(user, "email", None) or "").strip()
            if user_email:
                return user_email
    return (getattr(admin, "email", None) or "").strip()


def _linked_admin_storage_email(db: Session, user: User) -> str:
    """
    Email lưu admin_users cho bản ghi liên kết shop.
    Nếu email shop đã dùng bởi admin khác (vd. admin /admin/login) → email nội bộ unique.
    OTP vẫn gửi users.email qua display_email_for_admin.
    """
    shop_email = (user.email or "").strip()
    if not shop_email or "@" not in shop_email:
        raise ValueError("Thành viên cần có email để gán quyền quản trị web.")

    taken = db.query(AdminUser).filter(AdminUser.email == shop_email).first()
    if taken is None:
        return shop_email

    base = f"linked-user-{user.id}@188.com.vn"
    candidate = base
    n = 0
    while db.query(AdminUser).filter(AdminUser.email == candidate).first():
        n += 1
        candidate = f"linked-user-{user.id}-{n}@188.com.vn"
    return candidate


def apply_linked_staff_role(
    db: Session,
    user: User,
    role: Optional[AdminRole],
    modules: Optional[List[str]],
) -> None:
    """
    role=None: gỡ liên kết.
    modules=None: chỉ preset theo role (xoá granular_permissions).
    modules=[...]: tùy chỉnh mục (ghi đè preset hiển thị quyền).
    """
    if role is None:
        row = db.query(AdminUser).filter(AdminUser.linked_user_id == user.id).first()
        if row:
            remove_linked_staff_admin_row(db, row)
            db.commit()
        return

    if role not in LINKABLE_ROLES:
        raise ValueError("Vai trò không được phép gán qua liên kết thành viên.")

    if not (user.email or "").strip() or "@" not in (user.email or ""):
        raise ValueError("Thành viên cần có email để gán quyền quản trị web.")

    granular = _resolved_granular(role, modules)

    existing = db.query(AdminUser).filter(AdminUser.linked_user_id == user.id).first()
    if existing:
        if existing.role == AdminRole.SUPER_ADMIN:
            raise ValueError("Không thể đổi vai trò liên kết của super_admin.")
        existing.role = role
        existing.is_active = True
        existing.granular_permissions = granular
        db.commit()
        return

    username = _random_username(user.id)
    while db.query(AdminUser).filter(AdminUser.username == username).first():
        username = _random_username(user.id)

    pwd = secrets.token_urlsafe(24)
    admin = AdminUser(
        username=username,
        email=_linked_admin_storage_email(db, user),
        password_hash=get_password_hash(pwd),
        full_name=user.full_name or username,
        phone=user.phone,
        role=role,
        is_active=True,
        linked_user_id=user.id,
        granular_permissions=granular,
    )
    db.add(admin)
    db.commit()
