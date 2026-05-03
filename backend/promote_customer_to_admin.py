#!/usr/bin/env python3
"""
Gán quyền quản trị cho một tài khoản khách (users.id):

  cd backend && python promote_customer_to_admin.py <user_id>

- Thêm cột admin_users.linked_user_id (SQL một lần) — xem scripts/add_admin_linked_user_id.sql
- Tạo hoặc cập nhật dòng admin_users: linked_user_id = user_id, email trùng user.email

Khách đăng nhập → Cá nhân → « Quản trị web » → lấy JWT admin (không cần /admin/login riêng).
"""
from __future__ import annotations

import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.admin import AdminUser, AdminRole
from app.models.user import User
from app.core.security import get_password_hash


def _random_username(uid: int) -> str:
    suf = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"cust_admin_{uid}_{suf}"


def promote(db: Session, user_id: int) -> None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise SystemExit(f"Không có users.id={user_id}")
    email = (user.email or "").strip()
    if not email or "@" not in email:
        raise SystemExit("User cần có email (dùng để khớp admin_users.email).")

    existing_link = db.query(AdminUser).filter(AdminUser.linked_user_id == user_id).first()
    if existing_link:
        print(f"Đã liên kết: admin_users.id={existing_link.id} username={existing_link.username}")
        return

    by_email = db.query(AdminUser).filter(AdminUser.email == email).first()
    if by_email:
        by_email.linked_user_id = user_id
        db.commit()
        print(f"Đã gán linked_user_id={user_id} cho admin hiện có id={by_email.id} username={by_email.username}")
        return

    username = _random_username(user_id)
    while db.query(AdminUser).filter(AdminUser.username == username).first():
        username = _random_username(user_id)

    pwd_internal = "".join(random.choices(string.ascii_letters + string.digits, k=24))
    admin = AdminUser(
        username=username,
        email=email,
        password_hash=get_password_hash(pwd_internal),
        full_name=user.full_name or username,
        phone=user.phone,
        role=AdminRole.ADMIN,
        is_active=True,
        linked_user_id=user_id,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    print(f"Đã tạo admin_users.id={admin.id} username={username} linked_user_id={user_id}")
    print("Mật khẩu đăng nhập /admin/login được tạo ngẫu nhiên — khách nên dùng menu « Quản trị web » sau khi đăng nhập.")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python promote_customer_to_admin.py <user_id>")
    uid = int(sys.argv[1])
    db = SessionLocal()
    try:
        promote(db, uid)
    finally:
        db.close()


if __name__ == "__main__":
    main()
