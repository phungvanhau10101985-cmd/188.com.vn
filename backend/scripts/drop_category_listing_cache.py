"""
Xóa bảng category_listing_cache (cache lưới SP danh mục — chỉ bản 09/06).

An toàn khi đang chạy code fe5ece1: bảng này không còn trong model/migration.

  cd backend && source .venv/bin/activate
  python scripts/drop_category_listing_cache.py --dry-run
  python scripts/drop_category_listing_cache.py --yes
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(BACKEND_ROOT, ".env"))

TABLE = "category_listing_cache"


def main() -> int:
    parser = argparse.ArgumentParser(description=f"DROP TABLE {TABLE} nếu tồn tại")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra, không xóa")
    parser.add_argument("--yes", action="store_true", help="Xóa không hỏi xác nhận")
    args = parser.parse_args()

    from sqlalchemy import inspect, text

    from app.db.session import engine

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    exists = TABLE in tables

    print(f"DATABASE: {engine.url.render_as_string(hide_password=True)}")
    print(f"Bảng {TABLE}: {'có' if exists else 'không tồn tại'}")

    if not exists:
        print("Không cần làm gì.")
        return 0

    row_count = None
    try:
        with engine.connect() as conn:
            row_count = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
    except Exception as exc:
        print(f"(Không đếm được row: {exc})")
    else:
        print(f"Số dòng cache: {row_count}")

    if args.dry_run:
        print("--dry-run: bỏ qua DROP TABLE.")
        return 0

    if not args.yes:
        answer = input(f"DROP TABLE {TABLE}? Gõ YES để xác nhận: ").strip()
        if answer != "YES":
            print("Đã hủy.")
            return 1

    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE} CASCADE"))

    print(f"Đã xóa bảng {TABLE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
