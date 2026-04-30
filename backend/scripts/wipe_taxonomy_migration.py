"""
Migration taxonomy (lần đầu — schema categories đã đổi):

  - DELETE FROM products (toàn bộ SP)
  - DROP + CREATE lại 7 bảng category / SEO (+ seo_clusters)

Không có trên API/web — chỉ chạy local / SSH khi chủ động.

DATABASE_URL trong backend/.env (hoặc môi trường).

  python scripts/wipe_taxonomy_migration.py           # xem đếm rồi chờ gõ YES
  python scripts/wipe_taxonomy_migration.py --yes     # không hỏi
  python scripts/wipe_taxonomy_migration.py --dry-run # chỉ in đếm, không ghi DB
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.taxonomy_migration_wipe import execute_taxonomy_migration_wipe  # noqa: E402


def _print_result(result: dict) -> None:
    print("\nĐếm bảng:")
    for t, n in sorted(result["wiped"].items()):
        print(f"   {t:<38} rows={n}")
    print(f"\ndropped: {result['dropped']}")
    print(f"created: {result['created']}")
    print(f"elapsed_ms: {result['elapsed_ms']}  dry_run={result['dry_run']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Wipe products + tái tạo bảng taxonomy (CLI only)")
    parser.add_argument("--yes", action="store_true", help="Bỏ hỏi xác nhận sau khi xem đếm")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in số row từng bảng, không ghi DB")
    args = parser.parse_args()

    db_url = str(engine.url)
    drv = engine.url.drivername

    print("=" * 60)
    pwd = engine.url.password
    safe_url = db_url.replace(str(pwd), "***") if pwd else db_url
    print(f" DATABASE: {safe_url}")
    print(f" Driver:   {drv}")
    print("=" * 60)

    host = (engine.url.host or "").lower()
    if drv.startswith("postgresql") and host and host not in ("localhost", "127.0.0.1", "::1"):
        print(f" [!] PostgreSQL không phải localhost ({host}). Chắc chắn đúng DB?")

    db = SessionLocal()
    try:
        result = execute_taxonomy_migration_wipe(db, dry_run=True)
    finally:
        db.close()
        engine.dispose()

    _print_result(result)

    if args.dry_run:
        print("\n -- dry-run: không ghi DB. --")
        return 0

    if not args.yes:
        ans = input('\n Gõ "YES" để thực sự WIPE (Enter = hủy): ').strip()
        if ans != "YES":
            print(" Đã hủy.")
            return 1

    db_run = SessionLocal()
    try:
        result_final = execute_taxonomy_migration_wipe(db_run, dry_run=False)
    finally:
        db_run.close()
        engine.dispose()

    _print_result(result_final)
    print("\n JSON:", json.dumps(result_final, indent=2, default=str))
    print("\n Xong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
