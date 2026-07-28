#!/usr/bin/env python3
"""Gộp admin liên kết trùng email shop → admin_users chính (chạy một lần trên VPS)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.admin import AdminUser
from app.models.user import User
from app.services.linked_admin_staff import display_email_for_admin, repair_linked_admin_for_user


def main() -> int:
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.email.isnot(None), User.email != "").all()
        merged = 0
        for user in users:
            before = db.query(AdminUser).filter(AdminUser.linked_user_id == user.id).first()
            after = repair_linked_admin_for_user(db, user)
            if after and before and before.id != after.id:
                merged += 1
                print(
                    f"user #{user.id} {user.email}: gộp admin id={before.id} → id={after.id} "
                    f"({display_email_for_admin(db, after)})"
                )
        print(f"Hoàn tất. Gộp {merged} liên kết.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
