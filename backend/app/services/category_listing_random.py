"""
Random toàn danh mục storefront — cache danh sách product_id, shuffle theo seed mỗi lượt xem.

Tránh ORDER BY md5/random() trên toàn bộ bảng mỗi request (chậm) và tránh chỉ trộn ~96 SP mới nhất.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Query, Session

from app.core.config import settings
from app.models.product import Product
from app.utils.ttl_cache import cache as ttl_cache


def category_listing_ids_cache_ttl_seconds() -> float:
    return float(getattr(settings, "STOREFRONT_LISTING_FILTER_CACHE_TTL_SECONDS", 600) or 600)


def _norm_opt(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def build_category_listing_ids_cache_key(
    *,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_active: Optional[bool] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    warehouse_clearance_only: bool = False,
) -> str:
    payload = {
        "v": 1,
        "category": _norm_opt(category),
        "subcategory": _norm_opt(subcategory),
        "sub_subcategory": _norm_opt(sub_subcategory),
        "shop_name": _norm_opt(shop_name),
        "shop_id": _norm_opt(shop_id),
        "style": _norm_opt(style),
        "shop_name_chinese": _norm_opt(shop_name_chinese),
        "chinese_name": _norm_opt(chinese_name),
        "pro_lower_price": _norm_opt(pro_lower_price),
        "pro_high_price": _norm_opt(pro_high_price),
        "min_price": min_price,
        "max_price": max_price,
        "is_active": is_active,
        "filter_size": _norm_opt(filter_size),
        "filter_color": _norm_opt(filter_color),
        "filter_style_tag": _norm_opt(filter_style_tag),
        "warehouse_clearance_only": bool(warehouse_clearance_only),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"category_listing_ids:{digest}"


def seeded_shuffle_product_ids(ids: List[int], seed: str) -> List[int]:
    """Cùng thuật toán md5(id:seed) như SQL — phân trang ổn định trong một lượt xem."""
    refresh = str(seed or "").strip()
    if not refresh or len(ids) <= 1:
        return list(ids)

    def sort_key(pid: int) -> str:
        return hashlib.md5(f"{pid}:{refresh}".encode("utf-8")).hexdigest()

    return sorted(ids, key=sort_key)


def _fetch_product_ids(query: Query) -> List[int]:
    rows = query.with_entities(Product.id).order_by(Product.id.asc()).all()
    out: List[int] = []
    for row in rows:
        try:
            pid = int(row[0])
        except (TypeError, ValueError, IndexError):
            continue
        if pid > 0:
            out.append(pid)
    return out


def paginate_seeded_random_category_listing(
    db: Session,
    query: Query,
    *,
    cache_key: str,
    search_refresh: str,
    skip: int,
    limit: int,
) -> Dict[str, Any]:
    ttl = category_listing_ids_cache_ttl_seconds()

    def _load_ids() -> List[int]:
        return _fetch_product_ids(query)

    if ttl <= 0:
        all_ids = _load_ids()
    else:
        all_ids = ttl_cache.get_or_fetch(cache_key, ttl, _load_ids)

    ordered = seeded_shuffle_product_ids(all_ids, search_refresh)
    total = len(ordered)
    page_ids = ordered[max(0, int(skip)) : max(0, int(skip)) + max(1, int(limit))]

    if not page_ids:
        products: List[Product] = []
    else:
        rows = db.query(Product).filter(Product.id.in_(page_ids)).all()
        by_id = {int(r.id): r for r in rows}
        products = [by_id[i] for i in page_ids if i in by_id]

    page_num = skip // limit + 1 if limit > 0 else 1
    total_pages = math.ceil(total / limit) if limit > 0 else 1
    return {
        "total": total,
        "products": products,
        "page": page_num,
        "size": limit,
        "total_pages": total_pages,
        "applied_query": None,
        "normalized_query": None,
        "suggested_queries": [],
        "suggested_categories": [],
        "redirect_path": None,
        "ai_processed": False,
    }
