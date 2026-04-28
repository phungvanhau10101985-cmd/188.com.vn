#!/usr/bin/env python3
"""
Script khởi tạo PostgreSQL: tạo database (nếu chưa có), tạo bảng, chạy migrations.
Chạy: python scripts/init_postgresql.py
Hoặc: cd backend && python -m scripts.init_postgresql

Yêu cầu: DATABASE_URL trong .env trỏ đến PostgreSQL.
"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def main():
    url = os.getenv("DATABASE_URL", "").strip()
    if not url or "postgresql" not in url and "postgres" not in url:
        print("❌ DATABASE_URL chưa cấu hình PostgreSQL.")
        print("   Thêm vào .env: DATABASE_URL=postgresql://user:password@host:5432/dbname")
        sys.exit(1)

    from sqlalchemy import create_engine
    from app.db.base import Base
    from app.core.config import settings

    print("🔧 Đang kết nối PostgreSQL...")
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
    )

    # Import models để đăng ký với Base.metadata
    from app import models  # noqa: F401
    _ = models

    print("📦 Đang tạo bảng...")
    Base.metadata.create_all(bind=engine)
    print("✅ Bảng đã tạo.")

    print("🔄 Đang chạy migrations...")
    try:
        from app.db.migrations import run_migrations
        run_migrations()
        print("✅ Migrations hoàn tất.")
    except Exception as e:
        print(f"⚠️  Migrations: {e}")

    print("\n✅ PostgreSQL đã sẵn sàng!")


if __name__ == "__main__":
    main()
