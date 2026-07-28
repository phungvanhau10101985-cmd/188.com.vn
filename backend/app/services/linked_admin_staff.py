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


def _normalize_email(email: Optional[str]) -> str:
    return (email or "").strip().lower()


def display_email_for_admin(db: Session, admin: AdminUser) -> str:
    """Email hiển thị / OTP: ưu tiên email đăng nhập shop khi có liên kết."""
    linked_id = getattr(admin, "linked_user_id", None)
    if linked_id:
        user = db.query(User).filter(User.id == int(linked_id)).first()
        if user:
            user_email = (getattr(user, "email", None) or "").strip()
            if user_email:
                return user_email
    return (getattr(admin, "email", None) or "").strip()


def repair_linked_admin_for_user(db: Session, user: User) -> Optional[AdminUser]:
    """
    Gộp admin liên kết trùng email shop vào bản admin_users chính (cùng email).
    Ví dụ: user #7 phungvanhau10101985@gmail.com đang gắn cust_admin placeholder
    → chuyển linked_user_id sang admin «admin» và xóa bản cust_admin thừa.
    """
    user_email = _normalize_email(getattr(user, "email", None))
    if not user_email or "@" not in user_email:
        return (
            db.query(AdminUser)
            .filter(AdminUser.linked_user_id == user.id, AdminUser.is_active.is_(True))
            .first()
        )

    linked = (
        db.query(AdminUser)
        .filter(AdminUser.linked_user_id == user.id, AdminUser.is_active.is_(True))
        .first()
    )
    canonical = (
        db.query(AdminUser)
        .filter(AdminUser.is_active.is_(True))
        .filter(AdminUser.email.ilike(user_email))
        .first()
    )

    if canonical and linked and canonical.id != linked.id:
        if linked.role == AdminRole.SUPER_ADMIN:
            return linked
        if canonical.linked_user_id is None:
            canonical.linked_user_id = user.id
        elif int(canonical.linked_user_id) != int(user.id):
            return linked
        remove_linked_staff_admin_row(db, linked)
        db.commit()
        db.refresh(canonical)
        return canonical

    if linked:
        current = _normalize_email(linked.email)
        if current != user_email:
            conflict = (
                db.query(AdminUser)
                .filter(AdminUser.email.ilike(user_email), AdminUser.id != linked.id)
                .first()
            )
            if conflict:
                return repair_linked_admin_for_user(db, user)
            linked.email = user.email.strip()
            db.commit()
            db.refresh(linked)
        return linked

    if canonical and canonical.linked_user_id is None:
        canonical.linked_user_id = user.id
        db.commit()
        db.refresh(canonical)
        return canonical

    return canonical


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
        repair_linked_admin_for_user(db, user)
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
        repair_linked_admin_for_user(db, user)
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
    repair_linked_admin_for_user(db, user)
