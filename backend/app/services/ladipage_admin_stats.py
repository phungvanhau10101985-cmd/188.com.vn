# backend/app/services/ladipage_admin_stats.py
"""Thống kê coverage ladipage cho admin."""
from __future__ import annotations

from typing import Any, Dict, Set

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.ladipage import Ladipage
from app.models.product import Product


def _single_ladipage_product_ids(db: Session, *, published_only: bool = False) -> Set[int]:
    q = db.query(Ladipage.product_ids).filter(
        Ladipage.source_type == "products",
        func.coalesce(func.json_array_length(Ladipage.product_ids), 0) == 1,
    )
    if published_only:
        q = q.filter(Ladipage.status == "published")
    out: Set[int] = set()
    for (raw,) in q.all():
        if not isinstance(raw, list) or len(raw) != 1:
            continue
        try:
            out.add(int(raw[0]))
        except (TypeError, ValueError):
            continue
    return out


def ladipage_admin_stats(db: Session, kind: str) -> Dict[str, Any]:
    k = (kind or "").strip()
    if k == "product_single":
        active_total = int(
            db.query(func.count(Product.id)).filter(Product.is_active.is_(True)).scalar() or 0
        )
        with_lp = _single_ladipage_product_ids(db, published_only=False)
        with_published = _single_ladipage_product_ids(db, published_only=True)
        pages_total = int(
            db.query(func.count(Ladipage.id))
            .filter(
                Ladipage.source_type == "products",
                func.coalesce(func.json_array_length(Ladipage.product_ids), 0) == 1,
            )
            .scalar()
            or 0
        )
        covered = len(with_lp)
        covered_published = len(with_published)
        return {
            "kind": k,
            "active_products_total": active_total,
            "products_with_ladipage": covered,
            "products_with_published_ladipage": covered_published,
            "products_without_ladipage": max(0, active_total - covered),
            "ladipage_pages_total": pages_total,
        }

    if k == "category":
        cat_total = int(
            db.query(func.count(Category.id)).filter(Category.level == 3).scalar() or 0
        )
        with_lp = int(
            db.query(func.count(func.distinct(Ladipage.category_id)))
            .filter(Ladipage.source_type == "category", Ladipage.category_id.isnot(None))
            .scalar()
            or 0
        )
        pages_total = int(
            db.query(func.count(Ladipage.id)).filter(Ladipage.source_type == "category").scalar() or 0
        )
        return {
            "kind": k,
            "category_l3_total": cat_total,
            "categories_with_ladipage": with_lp,
            "categories_without_ladipage": max(0, cat_total - with_lp),
            "ladipage_pages_total": pages_total,
        }

    if k == "products_multi":
        pages_total = int(
            db.query(func.count(Ladipage.id))
            .filter(
                Ladipage.source_type == "products",
                func.coalesce(func.json_array_length(Ladipage.product_ids), 0) > 1,
            )
            .scalar()
            or 0
        )
        product_ids: Set[int] = set()
        rows = (
            db.query(Ladipage.product_ids)
            .filter(
                Ladipage.source_type == "products",
                func.coalesce(func.json_array_length(Ladipage.product_ids), 0) > 1,
            )
            .all()
        )
        for (raw,) in rows:
            if not isinstance(raw, list):
                continue
            for item in raw:
                try:
                    product_ids.add(int(item))
                except (TypeError, ValueError):
                    continue
        return {
            "kind": k,
            "ladipage_pages_total": pages_total,
            "products_in_multi_ladipages": len(product_ids),
        }

    return {"kind": k}
