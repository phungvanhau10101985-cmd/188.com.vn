"""
Gắn `category_level1_slug`, `category_level2_slug` vào payload Product (từ full_slug của category SP).
Cat2 = segment thứ 2 của full_slug (`cat1/cat2` hoặc `cat1/cat2/cat3`) — chỉ các cặp override trên frontend mới có trang riêng.
"""

from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product as ProductModel


def _slug_segments(full_slug: Optional[str]) -> Tuple[str, Optional[str]]:
    """Segment 1 (slug cat1) và segment 2 (slug cat2) nếu có."""
    if not full_slug or not str(full_slug).strip():
        return (None, None)
    parts = [p.strip() for p in str(full_slug).strip().split("/") if p.strip()]
    if not parts:
        return (None, None)
    c1 = parts[0]
    c2 = parts[1] if len(parts) >= 2 else None
    return (c1, c2)


def enrich_product_payloads_with_category_size_guide(
    db: Session,
    products: List[ProductModel],
    payloads: List[dict],
) -> None:
    """Sửa tại chỗ các dict đã model_dump(); thêm slug cat1 + cat2 từ `Category.full_slug`."""
    if len(products) != len(payloads):
        return
    n = len(products)
    if n == 0:
        return

    cat_ids: Set[int] = set()
    for p in products:
        if p.category_id:
            cat_ids.add(int(p.category_id))

    id_to_full: Dict[int, str] = {}
    if cat_ids:
        rows = db.query(Category.id, Category.full_slug).filter(Category.id.in_(cat_ids)).all()
        id_to_full = {int(r.id): (r.full_slug or "") for r in rows}

    name_fallback: Set[str] = set()
    for p in products:
        if not p.category_id and p.category and str(p.category).strip():
            name_fallback.add(str(p.category).strip())

    name_to_slug: Dict[str, str] = {}
    if name_fallback:
        c1n = (
            db.query(Category.name, Category.slug)
            .filter(Category.level == 1, Category.name.in_(name_fallback))
            .all()
        )
        for row in c1n:
            name_to_slug[str(row.name).strip()] = str(row.slug)

    for i in range(n):
        p = products[i]
        slug_cat1: Optional[str] = None
        slug_cat2: Optional[str] = None
        if p.category_id:
            fs = id_to_full.get(int(p.category_id))
            c1, c2 = _slug_segments(fs)
            slug_cat1, slug_cat2 = c1, c2
        if not slug_cat1 and p.category and str(p.category).strip():
            slug_cat1 = name_to_slug.get(str(p.category).strip())
        payloads[i]["category_level1_slug"] = slug_cat1
        payloads[i]["category_level2_slug"] = slug_cat2
