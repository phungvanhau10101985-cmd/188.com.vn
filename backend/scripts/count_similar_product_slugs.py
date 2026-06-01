#!/usr/bin/env python3
"""Đếm SP có slug giống >= ngưỡng (SequenceMatcher) với slug nguồn — cùng logic OOS redirect."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env")
load_dotenv(BACKEND / ".env.local")

from app.crud.product import (
    PRODUCT_OOS_GROUP_SLUG_MIN_SIMILARITY,
    find_similar_product_slug_for_oos_redirect,
    get_product_by_slug,
    product_slug_name_prefix,
    product_slug_oos_search_pool_prefix,
    score_product_slug_oos_similarity,
)
from app.db.session import SessionLocal
from app.models.product import Product


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("--min", type=float, default=PRODUCT_OOS_GROUP_SLUG_MIN_SIMILARITY)
    parser.add_argument("--active-only", action="store_true", help="Chỉ is_active=True")
    parser.add_argument("--limit-list", type=int, default=50)
    args = parser.parse_args()

    source = (args.slug or "").strip()
    min_sim = max(0.0, min(1.0, float(args.min)))
    db = SessionLocal()
    try:
        current = get_product_by_slug(db, source)
        pid = getattr(current, "product_id", None) if current else None
        name_prefix = product_slug_name_prefix(source, pid)
        pool_prefix = product_slug_oos_search_pool_prefix(db, name_prefix, source_slug=source)
        canonical = f"{name_prefix}-"
        redirect = find_similar_product_slug_for_oos_redirect(
            db, slug=source, min_similarity=min_sim, product_id=pid
        )

        print(f"SOURCE: {source}")
        print(f"NAME_PREFIX: {name_prefix}")
        print(f"POOL_ILIKE: {pool_prefix}%")
        print(f"CANONICAL_GROUP: {canonical}")
        print(f"MIN_SIMILARITY: {min_sim}")
        print(f"REDIRECT_TARGET: {redirect or '(none)'}")
        if current:
            print(
                f"EXACT_MATCH: id={current.id} available={current.available} "
                f"active={current.is_active} product_id={current.product_id}"
            )
        else:
            print("EXACT_MATCH: (không có trong DB)")

        q = db.query(Product).filter(
            Product.slug.isnot(None),
            Product.slug != "",
            Product.slug != source,
        )
        if args.active_only:
            q = q.filter(Product.is_active.is_(True))
        if pool_prefix:
            q = q.filter(Product.slug.ilike(f"{pool_prefix}%"))
        pool_candidates = q.all()
        print(f"POOL_ILIKE_CANDIDATES: {len(pool_candidates)}")

        matched: list[tuple[float, Product]] = []
        for p in pool_candidates:
            cand = (p.slug or "").strip()
            if not cand:
                continue
            sim = score_product_slug_oos_similarity(source, cand, name_prefix)
            if sim >= min_sim:
                matched.append((sim, p))

        matched.sort(key=lambda x: (-x[0], -(int(x[1].available or 0)), -(int(x[1].purchases or 0)), x[1].id))
        in_stock = sum(1 for _, p in matched if int(p.available or 0) > 0)

        print(f"MATCH_GE_{int(min_sim * 100)}PCT: {len(matched)}")
        print(f"IN_STOCK_MATCH: {in_stock}")
        print("---")
        for sim, p in matched[: args.limit_list]:
            print(
                f"{sim:.4f} | id={p.id} | avail={p.available} | active={p.is_active} | {p.slug}"
            )
        if len(matched) > args.limit_list:
            print(f"... và {len(matched) - args.limit_list} slug khác")
    finally:
        db.close()


if __name__ == "__main__":
    main()
