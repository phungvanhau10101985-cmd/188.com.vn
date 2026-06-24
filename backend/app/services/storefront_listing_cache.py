"""
Cache in-process (singleflight) cho listing storefront có bộ lọc — giảm query lặp PDP / danh mục.

Chỉ cache kết quả thô từ crud.product.get_products (trước serialize theo user).
Serialize + enrich sale vẫn chạy mỗi request — đúng giá sale cá nhân.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional

from app.core.config import settings
from app.utils.ttl_cache import cache as ttl_cache


def listing_filter_cache_ttl_seconds() -> float:
    return float(getattr(settings, "STOREFRONT_LISTING_FILTER_CACHE_TTL_SECONDS", 600) or 600)


def _norm_opt(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def build_listing_filter_cache_key(
    *,
    skip: int,
    limit: int,
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
    sort: Optional[str] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    skip_total: bool = False,
) -> str:
    payload = {
        "skip": int(skip),
        "limit": int(limit),
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
        "sort": _norm_opt(sort),
        "filter_size": _norm_opt(filter_size),
        "filter_color": _norm_opt(filter_color),
        "filter_style_tag": _norm_opt(filter_style_tag),
        "skip_total": bool(skip_total),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"listing_filter:{digest}"


def should_use_listing_filter_cache(
    *,
    admin_list: bool,
    raw_q: str,
    pid: str,
    order_random: bool,
    warehouse_clearance_only: bool,
    skip_total: bool,
    skip: int,
    limit: int,
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
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    sort: Optional[str] = None,
) -> bool:
    if admin_list or raw_q or pid or order_random or warehouse_clearance_only:
        return False
    sort_norm = (sort or "").strip().lower()
    if sort_norm == "random":
        return False
    if not skip_total or skip > 0 or limit > 120:
        return False
    text_filters = (
        category,
        subcategory,
        sub_subcategory,
        shop_name,
        shop_id,
        style,
        shop_name_chinese,
        chinese_name,
        pro_lower_price,
        pro_high_price,
        filter_size,
        filter_color,
        filter_style_tag,
    )
    if not any(x is not None and str(x).strip() for x in text_filters):
        return False
    if min_price is not None or max_price is not None:
        return True
    return True


def get_or_fetch_listing_raw(
    cache_key: str,
    fetcher: Callable[[], dict],
) -> dict:
    ttl = listing_filter_cache_ttl_seconds()
    if ttl <= 0:
        return fetcher()

    def _cached_fetch() -> dict:
        result = fetcher()
        return slim_listing_result_for_cache(result)

    slim = ttl_cache.get_or_fetch(cache_key, ttl, _cached_fetch)
    return deepcopy(slim)


def slim_listing_result_for_cache(result: dict) -> dict:
    """Chỉ lưu id + metadata — ORM không an toàn qua TTL cache."""
    products = result.get("products") or []
    ids: List[int] = []
    for row in products:
        try:
            ids.append(int(getattr(row, "id", row.get("id") if isinstance(row, dict) else 0)))
        except (TypeError, ValueError):
            continue
    slim = {k: v for k, v in result.items() if k != "products"}
    slim["product_ids"] = ids
    return slim


def hydrate_listing_result_from_cache(db, slim: dict):
    """Nạp lại ORM Product theo thứ tự product_ids."""
    from app.models.product import Product

    ids = [int(x) for x in (slim.get("product_ids") or []) if int(x) > 0]
    if not ids:
        out = dict(slim)
        out.pop("product_ids", None)
        out["products"] = []
        return out
    rows = db.query(Product).filter(Product.id.in_(ids)).all()
    by_id = {int(r.id): r for r in rows}
    products = [by_id[i] for i in ids if i in by_id]
    out = {k: v for k, v in slim.items() if k != "product_ids"}
    out["products"] = products
    return out


def invalidate_all_listing_filter_cache() -> None:
    ttl_cache.invalidate_all()
