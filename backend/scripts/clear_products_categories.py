"""
backend/scripts/clear_products_categories.py

Xóa SẠCH dữ liệu liên quan tới sản phẩm và danh mục trên DATABASE đang trỏ tới (DATABASE_URL).
PHẢI dùng có ý thức: thường chỉ chạy trên môi trường DEV/LOCAL.

Các bảng được xóa (theo nhóm):
  1) Sản phẩm/đánh giá/câu hỏi:     products, product_reviews, product_review_useful_votes,
                                    product_questions, product_question_useful_votes
  2) Tương tác sản phẩm/danh mục:   user_product_views, user_favorites, user_category_views,
                                    user_brand_views, user_search_history, user_shop_interactions,
                                    guest_product_views, guest_favorites, guest_search_history,
                                    cart_items, carts, search_logs, search_mappings,
                                    search_query_mappings, analytics_events
  3) Danh mục + SEO danh mục:       categories, category_seo_mappings, category_seo_meta,
                                    category_seo_dictionary, category_final_mappings,
                                    category_transform_rules
                                    (bỏ qua nếu có --keep-categories)

Các bảng KHÔNG bị động: users, admin_users, orders, payments, loyalty_tiers, bank_accounts,
                       site_embed_codes, notifications, user_addresses, user_trusted_devices,
                       email_*, push_subscriptions...

Cách dùng:
  python scripts/clear_products_categories.py                 # in danh sách + chờ gõ YES
  python scripts/clear_products_categories.py --yes           # bỏ qua confirm (CI/script)
  python scripts/clear_products_categories.py --dry-run       # chỉ in COUNT(*) từng bảng
  python scripts/clear_products_categories.py --keep-views       # KHÔNG xóa nhóm 2 (tương tác)
  python scripts/clear_products_categories.py --keep-categories  # chỉ xóa SP + phụ thuộc; GIỮ categories + SEO danh mục
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

# Đảm bảo import được module "app.*" khi chạy ngoài uvicorn.
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import text  # noqa: E402

from app.db.session import engine, SessionLocal  # noqa: E402


# Thứ tự xóa: bảng phụ thuộc xóa trước (CHILD trước, PARENT sau).
GROUP_PRODUCTS = [
    "product_review_useful_votes",
    "product_reviews",
    "product_question_useful_votes",
    "product_questions",
]
GROUP_INTERACTIONS = [
    "cart_items",
    "carts",
    "user_product_views",
    "user_favorites",
    "user_category_views",
    "user_brand_views",
    "user_search_history",
    "user_shop_interactions",
    "guest_product_views",
    "guest_favorites",
    "guest_search_history",
    "search_logs",
    "search_mappings",
    "search_query_mappings",
    "analytics_events",
]
GROUP_CATEGORIES = [
    "category_seo_mappings",
    "category_seo_meta",
    "category_seo_dictionary",
    "category_final_mappings",
    "category_transform_rules",
    "categories",
]
TABLE_PRODUCTS_LAST = ["products"]


def existing_tables() -> set:
    insp_sql = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema()"
    )
    if engine.url.drivername.startswith("sqlite"):
        insp_sql = "SELECT name AS table_name FROM sqlite_master WHERE type='table'"
    with engine.connect() as conn:
        rows = conn.execute(text(insp_sql)).all()
    return {r[0] for r in rows}


def count_rows(tables: List[str]) -> List[tuple]:
    out = []
    with engine.connect() as conn:
        for t in tables:
            try:
                n = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() or 0
            except Exception as e:
                n = f"ERR: {e}"
            out.append((t, n))
    return out


def truncate_postgres(tables: List[str]) -> None:
    """TRUNCATE ... CASCADE RESTART IDENTITY — Postgres only, nhanh và reset auto-id."""
    if not tables:
        return
    with engine.begin() as conn:
        joined = ", ".join(f'"{t}"' for t in tables)
        conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))


def delete_sqlite(tables: List[str]) -> None:
    """SQLite: DELETE từng bảng, rồi reset sqlite_sequence."""
    with engine.begin() as conn:
        for t in tables:
            conn.execute(text(f'DELETE FROM "{t}"'))
            try:
                conn.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{t}'"))
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Xóa dữ liệu sản phẩm/danh mục cục bộ")
    parser.add_argument("--yes", action="store_true", help="Không hỏi xác nhận")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in COUNT(*) từng bảng")
    parser.add_argument("--keep-views", action="store_true", help="Giữ lại nhóm tương tác/cart/search")
    parser.add_argument(
        "--keep-categories",
        action="store_true",
        help="Không xóa categories và các bảng SEO danh mục (category_*); chỉ xóa sản phẩm và phụ thuộc",
    )
    args = parser.parse_args()

    db_url = str(engine.url)
    drv = engine.url.drivername
    is_sqlite = drv.startswith("sqlite")
    is_pg = drv.startswith("postgresql")

    print("=" * 60)
    print(f" DATABASE: {db_url}")
    print(f" Driver:   {drv}")
    print("=" * 60)

    # Cảnh báo nếu URL trỏ tới host xa (rất có thể là production)
    host = (engine.url.host or "").lower()
    suspicious_hosts = [h for h in [host] if h and h not in ("", "localhost", "127.0.0.1", "::1")]
    if suspicious_hosts and not is_sqlite:
        print(f" [!] Host DB không phải localhost ({host}). Có chắc đang chạy trên môi trường DEV?")

    avail = existing_tables()
    targets: List[str] = []
    targets.extend([t for t in GROUP_PRODUCTS if t in avail])
    if not args.keep_views:
        targets.extend([t for t in GROUP_INTERACTIONS if t in avail])
    targets.extend([t for t in TABLE_PRODUCTS_LAST if t in avail])
    if not args.keep_categories:
        targets.extend([t for t in GROUP_CATEGORIES if t in avail])

    if not targets:
        print(" Không tìm thấy bảng nào để xóa. (DB trống hoặc chưa migrate?)")
        return 0

    print(" Bảng sẽ xử lý (theo thứ tự):")
    for row in count_rows(targets):
        print(f"   - {row[0]:<35}  rows={row[1]}")

    if args.dry_run:
        print("\n -- DRY RUN: không xóa gì. --")
        return 0

    if not args.yes:
        ans = input('\n Gõ "YES" để xác nhận xóa (Enter = hủy): ').strip()
        if ans != "YES":
            print(" Đã hủy.")
            return 1

    print("\n Đang xóa...")
    if is_pg:
        truncate_postgres(targets)
    elif is_sqlite:
        delete_sqlite(targets)
    else:
        # Khác: dùng DELETE thường, không reset auto-id.
        with engine.begin() as conn:
            for t in reversed(targets):  # CHILD trước (đã sắp), reverse để chắc
                conn.execute(text(f'DELETE FROM "{t}"'))

    print(" Xong. Kiểm tra lại COUNT:")
    for row in count_rows(targets):
        print(f"   - {row[0]:<35}  rows={row[1]}")

    # Đóng connection pool gọn gàng
    SessionLocal.remove() if hasattr(SessionLocal, "remove") else None
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
