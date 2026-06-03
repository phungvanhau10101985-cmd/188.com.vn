"""Kiểm tra tìm «sale» trên DB thực tế — chạy: cd backend && python scripts/debug_sale_search_db.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, or_, cast, String

from app.db.session import SessionLocal
from app.models.product import Product
from app.crud.product import (
    apply_product_search_word_filters,
    get_products,
    normalize_search_query,
)
from app.services.warehouse_clearance import is_sale_listing_search_query


def main() -> None:
    db = SessionLocal()
    try:
        url = str(db.bind.url) if db.bind else "?"
        # Che mật khẩu khi in
        safe_url = url.split("@")[-1] if "@" in url else url
        print(f"DB: ...@{safe_url}\n")

        active = (
            db.query(func.count(Product.id))
            .filter(Product.is_active.is_(True))
            .scalar()
        )
        print(f"SP is_active=true: {active}")

        name_sale = (
            db.query(func.count(Product.id))
            .filter(Product.is_active.is_(True), func.lower(Product.name).like("%sale%"))
            .scalar()
        )
        print(f"Tên chứa «sale» (active): {name_sale}")

        slug_sale = (
            db.query(func.count(Product.id))
            .filter(Product.is_active.is_(True), func.lower(Product.slug).like("%sale%"))
            .scalar()
        )
        print(f"Slug chứa «sale» (active): {slug_sale}")

        wh_active = (
            db.query(func.count(Product.id))
            .filter(
                Product.is_warehouse_clearance.is_(True),
                Product.is_active.is_(True),
                Product.available > 0,
            )
            .scalar()
        )
        print(f"Dòng kho thanh lý (active, tồn>0): {wh_active}")

        print("\n--- 5 SP tên có «sale» ---")
        rows = (
            db.query(Product.id, Product.product_id, Product.name, Product.is_warehouse_clearance)
            .filter(Product.is_active.is_(True), func.lower(Product.name).like("%sale%"))
            .limit(5)
            .all()
        )
        for r in rows:
            name = (r.name or "")[:70]
            print(f"  id={r.id} wh={r.is_warehouse_clearance} pid={r.product_id} | {name}")

        print("\n--- search_mapping keyword_input=sale ---")
        try:
            from app.models.search_mapping import SearchMapping

            m = db.query(SearchMapping).filter(SearchMapping.keyword_input == "sale").first()
            if m:
                print(f"  type={m.type} target={m.keyword_target!r}")
            else:
                print("  (không có)")
        except Exception as e:
            print(f"  skip: {e}")

        print("\n--- product_search_cache (norm q=sale, 1 row) ---")
        try:
            from app.crud import product_search_cache as psc

            key = psc.build_cache_key(norm_q="sale", skip=0, limit=12, category=None, subcategory=None,
                sub_subcategory=None, shop_name=None, shop_id=None, style=None,
                shop_name_chinese=None, chinese_name=None, pro_lower_price=None,
                pro_high_price=None, min_price=None, max_price=None, is_active=True,
                sort="id_desc", filter_size=None, filter_color=None, filter_style_tag=None)
            cached = psc.get_cached_result(db, key)
            if cached:
                print(f"  CACHE HIT total={cached.get('total')} redirect={cached.get('redirect_path')}")
            else:
                print("  (không cache hoặc hết hạn)")
        except Exception as e:
            print(f"  skip: {e}")

        print("\n--- get_products(q=sale, limit=5) ---")
        print(f"  is_sale_listing_search_query('sale') = {is_sale_listing_search_query('sale')}")
        result = get_products(db, q="sale", limit=5, skip=0, is_active=True)
        print(f"  total={result.get('total')} redirect_path={result.get('redirect_path')!r}")
        print(f"  word_filter count (see above section)")
        for p in (result.get("products") or [])[:5]:
            print(f"    - {(getattr(p, 'name', None) or '')[:65]}")

        print("\n--- apply_product_search_word_filters (từ «Sale») ---")
        base = db.query(Product).filter(Product.is_active.is_(True))
        from app.services.warehouse_clearance import apply_catalog_visibility_filter

        base = apply_catalog_visibility_filter(base, has_text_search=True)
        words = [w.strip() for w in normalize_search_query("sale").split() if w.strip()]
        qf = apply_product_search_word_filters(base, words)
        cnt = qf.count()
        print(f"  words={words!r} count={cnt}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
