"""
Xóa bản ghi danh mục / SEO / mapping khi không còn sản phẩm active khớp đường danh mục.
"""
from __future__ import annotations

from typing import Dict, List

from sqlalchemy.orm import Session

from app.crud.product import (
    _normalize_category_url_slug,
    count_products_for_category_path,
    get_category_tree_from_products,
    resolve_category_breadcrumb_names_from_tree,
)
from app.models.category import Category
from app.models.category_final_mapping import CategoryFinalMapping
from app.models.category_seo import CategorySeoMapping, CategorySeoMeta
from app.models.product import Product
from app.models.user import UserCategoryView


def _split_slug_parts(path: str) -> List[str]:
    return [p.strip().lower() for p in (path or "").split("/") if p.strip()]


def cleanup_empty_categories(db: Session, dry_run: bool = False) -> Dict[str, int]:
    """
    - categories: xóa dòng không còn product.category_id trỏ tới (đã xóa view user_category_views liên quan).
    - category_seo_meta, category_seo_mappings (source_path): xóa nếu path không resolve được trong cây đầy đủ
      hoặc đếm SP active = 0.
    - category_final_mappings: xóa nếu bộ đích (to_*) không còn SP active.
    """
    stats = {
        "categories": 0,
        "user_category_views": 0,
        "category_seo_meta": 0,
        "category_seo_mappings": 0,
        "category_final_mappings": 0,
    }

    used_rows = db.query(Product.category_id).filter(Product.category_id.isnot(None)).distinct().all()
    used_ids = {r[0] for r in used_rows}

    q_orphan = db.query(Category)
    if used_ids:
        q_orphan = q_orphan.filter(~Category.id.in_(used_ids))
    orphans: List[Category] = q_orphan.all()
    orphan_ids = [c.id for c in orphans]

    if orphan_ids:
        n_views = (
            db.query(UserCategoryView)
            .filter(UserCategoryView.category_id.in_(orphan_ids))
            .delete(synchronize_session=False)
        )
        stats["user_category_views"] = int(n_views or 0)
        for c in orphans:
            db.delete(c)
            stats["categories"] += 1

    tree_full = get_category_tree_from_products(db, is_active=True, hide_empty_branches=False)

    for meta in list(db.query(CategorySeoMeta).all()):
        parts = _split_slug_parts(meta.category_path)
        if not parts:
            db.delete(meta)
            stats["category_seo_meta"] += 1
            continue
        s1 = _normalize_category_url_slug(parts[0]) or ""
        s2 = _normalize_category_url_slug(parts[1]) if len(parts) > 1 else None
        s3 = _normalize_category_url_slug(parts[2]) if len(parts) > 2 else None
        bc = resolve_category_breadcrumb_names_from_tree(tree_full, s1, s2, s3)
        if not bc:
            db.delete(meta)
            stats["category_seo_meta"] += 1
            continue
        ln = len(bc)
        cnt = count_products_for_category_path(
            db,
            bc[0],
            bc[1] if ln > 1 else None,
            bc[2] if ln > 2 else None,
            True,
        )
        if cnt == 0:
            db.delete(meta)
            stats["category_seo_meta"] += 1

    for row in list(db.query(CategorySeoMapping).all()):
        parts = _split_slug_parts(row.source_path or "")
        if not parts:
            db.delete(row)
            stats["category_seo_mappings"] += 1
            continue
        s1 = _normalize_category_url_slug(parts[0]) or ""
        s2 = _normalize_category_url_slug(parts[1]) if len(parts) > 1 else None
        s3 = _normalize_category_url_slug(parts[2]) if len(parts) > 2 else None
        bc = resolve_category_breadcrumb_names_from_tree(tree_full, s1, s2, s3)
        if not bc:
            db.delete(row)
            stats["category_seo_mappings"] += 1
            continue
        ln = len(bc)
        cnt = count_products_for_category_path(
            db,
            bc[0],
            bc[1] if ln > 1 else None,
            bc[2] if ln > 2 else None,
            True,
        )
        if cnt == 0:
            db.delete(row)
            stats["category_seo_mappings"] += 1

    for m in list(db.query(CategoryFinalMapping).all()):
        tc = (m.to_category or "").strip()
        ts = (m.to_subcategory or "").strip()
        tss = (m.to_sub_subcategory or "").strip()
        if not tc:
            db.delete(m)
            stats["category_final_mappings"] += 1
            continue
        if tss and ts:
            cnt = count_products_for_category_path(db, tc, ts, tss, True)
        elif ts:
            cnt = count_products_for_category_path(db, tc, ts, None, True)
        else:
            cnt = count_products_for_category_path(db, tc, None, None, True)
        if cnt == 0:
            db.delete(m)
            stats["category_final_mappings"] += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return stats
