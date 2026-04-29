"""
Chạy từ thư mục backend:

  python scripts/cleanup_empty_categories_db.py           # preview / chờ YES
  python scripts/cleanup_empty_categories_db.py --yes      # xóa ngay
  python scripts/cleanup_empty_categories_db.py --dry-run  # chỉ rollback, không persist

Xóa:
  - categories không được product.category_id nào trỏ tới (và view danh mục user liên quan)
  - category_seo_meta, category_seo_mappings (path nguồn), category_final_mappings khi không còn SP active
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.category_empty_cleanup import cleanup_empty_categories  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Xóa danh mục / mapping SEO không còn sản phẩm")
    parser.add_argument("--yes", action="store_true", help="Không hỏi xác nhận")
    parser.add_argument("--dry-run", action="store_true", help="Chạy xong rollback (không ghi DB)")
    args = parser.parse_args()

    db_url = str(engine.url)
    host = (engine.url.host or "").lower()
    print("=" * 60)
    print(f" DATABASE: {db_url}")
    if host and host not in ("localhost", "127.0.0.1", "::1"):
        print(f" [!] Host không phải localhost ({host}). Kiểm tra kỹ trước khi xóa.")

    if not args.yes and not args.dry_run:
        ans = input('\n Gõ "YES" để xác nhận xóa (Enter = hủy): ').strip()
        if ans != "YES":
            print(" Đã hủy.")
            return 1

    db = SessionLocal()
    try:
        stats = cleanup_empty_categories(db, dry_run=args.dry_run)
        action = "DRY RUN (rollback)" if args.dry_run else "Đã ghi DB"
        print(f"\n {action}")
        for k, v in sorted(stats.items()):
            print(f"   {k}: {v}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
