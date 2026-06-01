#!/usr/bin/env python3
"""
Thử: URL không khớp DB → DeepSeek một dòng từ khóa → search.
Chạy: cd backend && python3 scripts/test_legacy_url_deepseek_keywords.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crud import product as product_crud
from app.crud.product import (
    _resolve_missing_product_listing_path,
    extract_legacy_url_name_prefix,
)
from app.db.session import SessionLocal
from app.services.legacy_oos_deepseek_keywords import deepseek_legacy_oos_search_query

LEGACY_PATH = (
    "moi-ma-b6761-gia-670k-quan-nam-jitde-hang-mua-he-phong-cach-tre-trung-"
    "phong-cach-han-quoc-thoi-trang-nam-chat-lieu-vai-bong-g02-san-pham-moi-"
    "mien-phi-van-chuyen-toan-quoc-1148637"
)
TAIL_ID = 1148637


def run_search(db, q: str, limit: int = 48) -> tuple[int, float]:
    t0 = time.perf_counter()
    result = product_crud.get_products(db, skip=0, limit=limit, is_active=True, q=q)
    return int(result.get("total") or 0), time.perf_counter() - t0


def main() -> int:
    print("=== Legacy URL DeepSeek (một dòng từ khóa) ===\n")

    db = SessionLocal()
    try:
        from app.models.product import Product

        p = db.query(Product).filter(Product.id == TAIL_ID).first()
        print(f"1) DB products.id={TAIL_ID}:", "CÓ" if p else "KHÔNG")

        rule_pool = extract_legacy_url_name_prefix(LEGACY_PATH)
        rule_q = (rule_pool or "").replace("-", " ")
        rule_total, rule_s = run_search(db, rule_q)
        print(f"\n2) Rule (không AI): q={rule_q!r} → {rule_total} SP ({rule_s:.2f}s)")

        print("\n3) DeepSeek một dòng...")
        t0 = time.perf_counter()
        try:
            ai_q = deepseek_legacy_oos_search_query(LEGACY_PATH)
        except Exception as exc:
            print(f"   LỖI: {exc}")
            return 1
        ai_s = time.perf_counter() - t0
        print(f"   {ai_s:.2f}s | từ khóa: {ai_q!r}")
        if ai_q:
            ai_total, ai_search_s = run_search(db, ai_q)
            print(f"   Search: {ai_total} SP ({ai_search_s:.2f}s)")

        t0 = time.perf_counter()
        path = _resolve_missing_product_listing_path(db, source_slug=LEGACY_PATH)
        path_s = time.perf_counter() - t0
        print(f"\n4) resolve_missing_product_listing_path: {path!r} ({path_s:.2f}s)")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
