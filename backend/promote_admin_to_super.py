#!/usr/bin/env python3
"""
Nâng một tài khoản admin_users lên super_admin (chạy trong thư mục backend):

  python promote_admin_to_super.py
  python promote_admin_to_super.py --username admin

Chỉ dùng khi bạn tin cậy tài khoản đó — super_admin chỉnh preset NV, tài khoản super khác, v.v.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.admin import AdminUser, AdminRole


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--username", default="admin", help="Username trong admin_users")
    args = p.parse_args()
    db = SessionLocal()
    try:
        u = db.query(AdminUser).filter(AdminUser.username == args.username.strip()).first()
        if not u:
            print(f"Không tìm thấy admin_users.username = {args.username!r}")
            sys.exit(1)
        old = u.role.value if hasattr(u.role, "value") else str(u.role)
        u.role = AdminRole.SUPER_ADMIN
        db.commit()
        print(f"Đã đổi {args.username!r}: {old} → super_admin")
    except Exception as e:
        print("Lỗi:", e)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
