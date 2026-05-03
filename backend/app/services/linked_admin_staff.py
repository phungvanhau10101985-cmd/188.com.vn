"""Gán / gỡ quyền quản trị web qua linked_user_id (users ↔ admin_users)."""
from __future__ import annotations

import random
import secrets
import string
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.admin_permissions import normalize_module_list
from app.models.admin import AdminUser, AdminRole
from app.models.user import User
from app.core.security import get_password_hash

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
            if row.role == AdminRole.SUPER_ADMIN:
                raise ValueError("Không thể gỡ liên kết tài khoản super_admin.")
            row.linked_user_id = None
            row.granular_permissions = None
            row.is_active = False
            db.commit()
        return

    if role not in LINKABLE_ROLES:
        raise ValueError("Vai trò không được phép gán qua liên kết thành viên.")

    email = (user.email or "").strip()
    if not email or "@" not in email:
        raise ValueError("Thành viên cần có email để gán quyền quản trị web.")

    granular = _resolved_granular(role, modules)

    existing = db.query(AdminUser).filter(AdminUser.linked_user_id == user.id).first()
    if existing:
        if existing.role == AdminRole.SUPER_ADMIN:
            raise ValueError("Không thể đổi vai trò liên kết của super_admin.")
        existing.role = role
        existing.email = email
        existing.is_active = True
        existing.granular_permissions = granular
        db.commit()
        return

    by_email = db.query(AdminUser).filter(AdminUser.email == email).first()
    if by_email:
        if by_email.role == AdminRole.SUPER_ADMIN:
            raise ValueError("Email này đã gắn super_admin — không liên kết qua thành viên.")
        by_email.linked_user_id = user.id
        by_email.role = role
        by_email.is_active = True
        by_email.granular_permissions = granular
        db.commit()
        return

    username = _random_username(user.id)
    while db.query(AdminUser).filter(AdminUser.username == username).first():
        username = _random_username(user.id)

    pwd = secrets.token_urlsafe(24)
    admin = AdminUser(
        username=username,
        email=email,
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
