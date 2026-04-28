#!/usr/bin/env python3
"""
Đặt lại mật khẩu admin (chạy từ thư mục backend):
  python reset_admin_password.py
  python reset_admin_password.py admin newpassword123
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.models.admin import AdminUser
from app.core.security import get_password_hash

def main():
    username = (sys.argv[1] if len(sys.argv) > 1 else "admin").strip()
    new_password = (sys.argv[2] if len(sys.argv) > 2 else "admin123").strip()
    if not new_password:
        print("Mật khẩu không được để trống.")
        return
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == username).first()
        if not admin:
            admin = db.query(AdminUser).filter(AdminUser.username == username.lower()).first()
        if not admin:
            print(f"Không tìm thấy admin với username: {username}")
            return
        admin.password_hash = get_password_hash(new_password)
        db.commit()
        print(f"Đã đặt lại mật khẩu cho '{admin.username}'. Mật khẩu mới: {new_password}")
    except Exception as e:
        print("Lỗi:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
