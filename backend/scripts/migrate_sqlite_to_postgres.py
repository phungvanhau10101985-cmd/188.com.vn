#!/usr/bin/env python3
"""
Script migrate dữ liệu từ SQLite sang PostgreSQL.
Chạy khi đã có DATABASE_URL PostgreSQL trong .env.

Cách dùng:
1. Cấu hình .env: DATABASE_URL=postgresql://...
2. Tạo file .env.migrate với SQLITE_SOURCE=sqlite:///./app.db (đường dẫn SQLite nguồn)
3. Chạy: SQLITE_SOURCE=sqlite:///./app.db python scripts/migrate_sqlite_to_postgres.py

Hoặc set biến môi trường SQLITE_SOURCE trước khi chạy.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()
load_dotenv(".env.migrate")  # Optional override


def main():
    sqlite_url = os.getenv("SQLITE_SOURCE", "sqlite:///./app.db").strip()
    pg_url = os.getenv("DATABASE_URL", "").strip()

    if not pg_url or "postgresql" not in pg_url and "postgres" not in pg_url:
        print("❌ DATABASE_URL phải trỏ đến PostgreSQL.")
        sys.exit(1)

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.db.base import Base
    from app.core.config import settings

    # Import all models
    from app import models  # noqa: F401

    print("📂 Nguồn SQLite:", sqlite_url)
    print("📂 Đích PostgreSQL:", pg_url[:50] + "...")

    src = create_engine(sqlite_url)
    dst = create_engine(pg_url, pool_pre_ping=True)

    # Tạo bảng trên PostgreSQL
    print("\n🔧 Tạo bảng trên PostgreSQL...")
    Base.metadata.create_all(bind=dst)

    # Danh sách bảng
    table_list = [t for t in Base.metadata.tables.keys() if t != "migration_history"]
    tables_to_truncate = [t for t in table_list]
    if tables_to_truncate:
        try:
            with dst.connect() as dconn:
                dconn.execute(text("TRUNCATE " + ", ".join(tables_to_truncate) + " RESTART IDENTITY CASCADE"))
                dconn.commit()
            print("  Đã xóa dữ liệu cũ (nếu có)")
        except Exception as e:
            print(f"  Truncate (bỏ qua nếu bảng trống): {e}")

    # Thứ tự migrate: cha trước, con sau (theo FK)
    migrate_order = [
        "categories", "category_seo_mappings", "category_seo_dictionary", "users", "admin_users",
        "user_addresses", "bank_accounts", "products", "carts", "cart_items",
        "orders", "order_items", "payments",
        "product_questions", "product_reviews", "product_question_useful_votes", "product_review_useful_votes",
        "user_product_views", "user_favorites", "user_category_views", "user_brand_views",
        "user_search_history", "user_shop_interactions"
    ]
    tables = [t for t in migrate_order if t in table_list]
    tables += [t for t in table_list if t not in tables]

    # Cột boolean: SQLite lưu 0/1, PostgreSQL cần True/False
    BOOLEAN_COLS = {
        "requires_deposit", "is_active", "is_imported", "deposit_require",
        "is_verified", "is_default"
    }
    # Từ khóa reserved PostgreSQL cần quote
    RESERVED_COLS = {"group", "order", "user"}

    def quote_col(c):
        return f'"{c}"' if c.lower() in RESERVED_COLS else c

    def sanitize_row(d, table):
        for k, v in list(d.items()):
            if v == "null" or (isinstance(v, str) and v.strip().lower() == "null"):
                d[k] = None
            elif k in BOOLEAN_COLS and v is not None:
                d[k] = bool(v) if isinstance(v, (int, float)) else (str(v).lower() in ("1", "true", "yes"))

    for table_name in tables:
        try:
            # Chỉ dùng cột có trong PostgreSQL (model) - bỏ cột thừa từ SQLite
            if table_name not in Base.metadata.tables:
                print(f"  ⏭️  {table_name}: không có trong metadata, bỏ qua")
                continue
            target_cols = set(c.name for c in Base.metadata.tables[table_name].columns)

            with src.connect() as sconn, dst.connect() as dconn:
                result = sconn.execute(text(f"SELECT * FROM {table_name}"))
                rows = result.fetchall()
                if not rows:
                    print(f"  ⏭️  {table_name}: 0 rows, bỏ qua")
                    continue

                src_cols = result.keys()
                # Chỉ lấy cột tồn tại ở cả source và target
                cols = [c for c in src_cols if c in target_cols]
                skipped = [c for c in src_cols if c not in target_cols]
                if skipped:
                    print(f"  📌 {table_name}: bỏ qua cột không có trong model: {skipped}")
                if not cols:
                    print(f"  ⚠️  {table_name}: không có cột chung, bỏ qua")
                    continue

                col_list = ", ".join(quote_col(c) for c in cols)
                placeholders = ", ".join([f":{c}" for c in cols])

                inserted = 0
                for row in rows:
                    row_dict = dict(zip(src_cols, row))
                    d = {k: row_dict[k] for k in cols}
                    sanitize_row(d, table_name)
                    try:
                        dconn.execute(
                            text(f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders})"),
                            d
                        )
                        dconn.commit()
                        inserted += 1
                    except Exception as e:
                        dconn.rollback()
                        print(f"    ⚠️ Row error: {e}")

                # Reset sequence cho cột id (PostgreSQL)
                if "id" in cols and inserted > 0:
                    try:
                        dconn.execute(text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 1))"))
                        dconn.commit()
                    except Exception:
                        pass
                print(f"  ✅ {table_name}: {inserted} rows")
        except Exception as e:
            print(f"  ❌ {table_name}: {e}")

    print("\n✅ Migration hoàn tất!")


if __name__ == "__main__":
    main()
