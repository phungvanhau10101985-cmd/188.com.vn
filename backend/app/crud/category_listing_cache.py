"""Cache JSON lưới sản phẩm danh mục storefront.

Khác `product_search_cache`: cache này chỉ dành cho `/products/` có category,
không có q/product_id/admin. Default random dùng một key ổn định để warmup nền
ghi đè lưới đã chuẩn bị cho lần mở sau.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.category_listing_cache import CategoryListingCache

logger = logging.getLogger(__name__)

_CACHE_QUERY_PAYLOAD_VERSION = 1
_SORT_RANDOM = "random"


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def category_path_from_parts(
    category: Optional[str],
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
) -> str:
    parts = [_clean(category), _clean(subcategory), _clean(sub_subcategory)]
    return "/".join([p for p in parts if p])


def category_paths_for_product_state(product: Any) -> List[str]:
    c1 = _clean(getattr(product, "category", None))
    c2 = _clean(getattr(product, "subcategory", None))
    c3 = _clean(getattr(product, "sub_subcategory", None))
    if not c1:
        return []
    paths = [category_path_from_parts(c1)]
    if c2:
        paths.append(category_path_from_parts(c1, c2))
    if c2 and c3:
        paths.append(category_path_from_parts(c1, c2, c3))
    return paths


def build_cache_query_payload(
    *,
    skip: int,
    limit: int,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    is_active: Optional[bool],
    sort: str = _SORT_RANDOM,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> Dict[str, Any]:
    sort_norm = (_clean(sort) or _SORT_RANDOM).lower()
    return {
        "sk": max(0, int(skip)),
        "li": max(1, int(limit)),
        "c1": _clean(category),
        "c2": _clean(subcategory),
        "c3": _clean(sub_subcategory),
        "min": "" if min_price is None else float(min_price),
        "max": "" if max_price is None else float(max_price),
        "ia": True if is_active is not False else False,
        "sort": sort_norm,
        "sz": _clean(filter_size),
        "cl": _clean(filter_color),
        "stylet": _clean(filter_style_tag),
        "pv": _CACHE_QUERY_PAYLOAD_VERSION,
    }


def build_cache_key(**kwargs: Any) -> str:
    payload = build_cache_query_payload(**kwargs)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _payload_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _opt_str(payload: Dict[str, Any], key: str) -> Optional[str]:
    value = _clean(payload.get(key))
    return value or None


def _opt_float(payload: Dict[str, Any], key: str) -> Optional[float]:
    value = payload.get(key)
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def payload_to_get_products_kwargs(
    payload: Dict[str, Any],
    *,
    random_seed: Optional[str] = None,
) -> Dict[str, Any]:
    from app.crud import product as product_crud

    return {
        "skip": max(0, int(payload.get("sk") or 0)),
        "limit": max(1, int(payload.get("li") or 96)),
        "category": _opt_str(payload, "c1"),
        "subcategory": _opt_str(payload, "c2"),
        "sub_subcategory": _opt_str(payload, "c3"),
        "min_price": _opt_float(payload, "min"),
        "max_price": _opt_float(payload, "max"),
        "is_active": True if payload.get("ia") is not False else False,
        "q": None,
        "product_id": None,
        "sort": product_crud.normalize_product_list_sort(str(payload.get("sort") or _SORT_RANDOM)),
        "order_random": False,
        "filter_size": _opt_str(payload, "sz"),
        "filter_color": _opt_str(payload, "cl"),
        "filter_style_tag": _opt_str(payload, "stylet"),
        "search_refresh": random_seed,
        "include_warehouse_products": False,
        "warehouse_clearance_only": False,
        "admin_list_query": False,
    }


def get_cached_result(db: Session, cache_key: str) -> Optional[Dict[str, Any]]:
    row = (
        db.query(CategoryListingCache)
        .filter(
            CategoryListingCache.cache_key == cache_key,
            CategoryListingCache.is_stale.is_(False),
        )
        .first()
    )
    if not row:
        return None
    try:
        data = json.loads(row.response_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    data["category_listing_cache_status"] = "hit"
    if row.updated_at is not None:
        data["category_listing_cache_updated_at"] = row.updated_at.isoformat()
    try:
        row.last_accessed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
    return data


def set_cached_result(
    db: Session,
    cache_key: str,
    response: Dict[str, Any],
    *,
    query_payload: Dict[str, Any],
) -> None:
    category_path = category_path_from_parts(
        query_payload.get("c1"),
        query_payload.get("c2"),
        query_payload.get("c3"),
    )
    if not category_path:
        return
    sort_norm = str(query_payload.get("sort") or _SORT_RANDOM)[:32]
    body = dict(response)
    body["category_listing_cache_status"] = "refreshed"
    response_json = json.dumps(body, ensure_ascii=False, default=str)
    query_json = _payload_json(query_payload)
    row = db.query(CategoryListingCache).filter(CategoryListingCache.cache_key == cache_key).first()
    try:
        if row:
            row.response_json = response_json
            row.cache_query_json = query_json
            row.category_path = category_path
            row.sort = sort_norm
            row.is_stale = False
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(
                CategoryListingCache(
                    cache_key=cache_key,
                    response_json=response_json,
                    cache_query_json=query_json,
                    category_path=category_path,
                    sort=sort_norm,
                    is_stale=False,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


def rebuild_category_listing_cache_response(
    db: Session,
    payload: Dict[str, Any],
    *,
    random_seed: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    from app.api.endpoints.products import _serialize_products_for_api
    from app.crud import product as product_crud

    kwargs = payload_to_get_products_kwargs(payload, random_seed=random_seed)
    result = product_crud.get_products(db, **kwargs)
    if not isinstance(result, dict) or result.get("redirect_path") or result.get("error"):
        return None
    if "products" in result:
        result["products"] = _serialize_products_for_api(
            db,
            result["products"],
            user=None,
            include_warehouse_clearance=True,
        )
    result["category_listing_cache_status"] = "refreshed"
    return result


def refresh_category_listing_cache(
    db: Session,
    payload: Dict[str, Any],
    *,
    random_seed: Optional[str] = None,
) -> bool:
    cache_key = build_cache_key(
        skip=int(payload.get("sk") or 0),
        limit=int(payload.get("li") or 96),
        category=_opt_str(payload, "c1"),
        subcategory=_opt_str(payload, "c2"),
        sub_subcategory=_opt_str(payload, "c3"),
        min_price=_opt_float(payload, "min"),
        max_price=_opt_float(payload, "max"),
        is_active=True if payload.get("ia") is not False else False,
        sort=str(payload.get("sort") or _SORT_RANDOM),
        filter_size=_opt_str(payload, "sz"),
        filter_color=_opt_str(payload, "cl"),
        filter_style_tag=_opt_str(payload, "stylet"),
    )
    response = rebuild_category_listing_cache_response(db, payload, random_seed=random_seed)
    if response is None:
        return False
    set_cached_result(db, cache_key, response, query_payload=payload)
    return True


def mark_stale_by_category_paths(db: Session, paths: Iterable[str]) -> int:
    unique_paths = sorted({_clean(path) for path in paths if _clean(path)})
    if not unique_paths:
        return 0
    try:
        count = (
            db.query(CategoryListingCache)
            .filter(
                CategoryListingCache.category_path.in_(unique_paths),
                CategoryListingCache.is_stale.is_(False),
            )
            .update({"is_stale": True}, synchronize_session=False)
        )
        db.commit()
        return int(count or 0)
    except Exception:
        db.rollback()
        raise


def mark_stale_for_product_states(db: Session, *product_states: Any) -> int:
    paths: List[str] = []
    for product in product_states:
        if product is not None:
            paths.extend(category_paths_for_product_state(product))
    return mark_stale_by_category_paths(db, paths)


def mark_all_stale(db: Session) -> int:
    try:
        count = (
            db.query(CategoryListingCache)
            .filter(or_(CategoryListingCache.is_stale.is_(False), CategoryListingCache.is_stale.is_(None)))
            .update({"is_stale": True}, synchronize_session=False)
        )
        db.commit()
        return int(count or 0)
    except Exception:
        db.rollback()
        raise
