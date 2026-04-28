#!/usr/bin/env python3
"""
Tạo admin đầu tiên (chạy từ thư mục backend):
  python create_first_admin.py
Mặc định: username=admin, password=admin123 - ĐỔI MẬT KHẨU SAU KHI ĐĂNG NHẬP.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.base import Base
from app.models.admin import AdminUser, AdminRole
from app.core.security import get_password_hash

def main():
    db = SessionLocal()
    try:
        existing = db.query(AdminUser).filter(AdminUser.username == "admin").first()
        if existing:
            print("Admin 'admin' đã tồn tại.")
            return
        admin = AdminUser(
            username="admin",
            email="admin@188.com.vn",
            password_hash=get_password_hash("admin123"),
            full_name="Administrator",
            role=AdminRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("Đã tạo admin: username=admin, password=admin123")
        print("Vui lòng đổi mật khẩu sau khi đăng nhập.")
    except Exception as e:
        print("Lỗi:", e)
        db.rollback()
        # Có thể bảng admin_users chưa có - tạo tất cả bảng
        from app.db.base import Base as ModelBase
        from app.db.session import engine
        import app.models  # noqa: F401 - đăng ký models với Base
        ModelBase.metadata.create_all(bind=engine)
        print("Đã tạo bảng. Chạy lại: python create_first_admin.py")
    finally:
        db.close()

if __name__ == "__main__":
    main()
