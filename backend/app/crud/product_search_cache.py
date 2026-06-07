"""
Đọc/ghi cache JSON kết quả GET /products/?q=... (payload trả về client sau khi serialize SP).

Mặc định cache vĩnh viễn (PRODUCT_SEARCH_CACHE_TTL_SECONDS=0) — làm mới JSON khi SP liên quan
từ khóa được thêm/xóa (refresh_caches_for_product_states).
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.product_search_cache import ProductSearchCache

logger = logging.getLogger(__name__)

# Legacy: TTL > 0 bật hết hạn theo giây; 0 = vĩnh viễn đến khi refresh.
DEFAULT_TTL_SECONDS = 0
_CACHE_QUERY_PAYLOAD_VERSION = 14


def _configured_ttl_seconds() -> Optional[int]:
    try:
        from app.core.config import settings

        v = int(getattr(settings, "PRODUCT_SEARCH_CACHE_TTL_SECONDS", DEFAULT_TTL_SECONDS))
        return None if v <= 0 else v
    except (TypeError, ValueError):
        return None


def _cache_is_active_filter(now: datetime):
    return or_(ProductSearchCache.expires_at.is_(None), ProductSearchCache.expires_at > now)


def build_cache_query_payload(
    *,
    norm_q: str,
    skip: int,
    limit: int,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    shop_name: Optional[str],
    shop_id: Optional[str],
    style: Optional[str],
    shop_name_chinese: Optional[str],
    chinese_name: Optional[str],
    pro_lower_price: Optional[str],
    pro_high_price: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    is_active: Optional[bool],
    sort: str = "id_desc",
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "q": norm_q or "",
        "sk": int(skip),
        "li": int(limit),
        "c1": (category or "").strip(),
        "c2": (subcategory or "").strip(),
        "c3": (sub_subcategory or "").strip(),
        "sn": (shop_name or "").strip(),
        "sid": (shop_id or "").strip(),
        "st": (style or "").strip(),
        "stc": (shop_name_chinese or "").strip(),
        "cn": (chinese_name or "").strip(),
        "pl": (pro_lower_price or "").strip(),
        "ph": (pro_high_price or "").strip(),
        "min": "" if min_price is None else float(min_price),
        "max": "" if max_price is None else float(max_price),
        "ia": True if is_active is not False else False,
        "sort": (sort or "").strip() or "id_desc",
        "sz": (filter_size or "").strip(),
        "cl": (filter_color or "").strip(),
        "stylet": (filter_style_tag or "").strip(),
        "pv": _CACHE_QUERY_PAYLOAD_VERSION,
    }


def build_cache_key(
    *,
    norm_q: str,
    skip: int,
    limit: int,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    shop_name: Optional[str],
    shop_id: Optional[str],
    style: Optional[str],
    shop_name_chinese: Optional[str],
    chinese_name: Optional[str],
    pro_lower_price: Optional[str],
    pro_high_price: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    is_active: Optional[bool],
    sort: str = "id_desc",
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> str:
    payload = build_cache_query_payload(
        norm_q=norm_q,
        skip=skip,
        limit=limit,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
        min_price=min_price,
        max_price=max_price,
        is_active=is_active,
        sort=sort,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    )
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def get_cached_result(db: Session, cache_key: str) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    row = (
        db.query(ProductSearchCache)
        .filter(ProductSearchCache.cache_key == cache_key, _cache_is_active_filter(now))
        .first()
    )
    if not row:
        return None
    try:
        return json.loads(row.response_json)
    except json.JSONDecodeError:
        return None


def _prune_expired(db: Session) -> None:
    """Chỉ áp dụng khi bật TTL; dọn dòng đã hết hạn."""
    if _configured_ttl_seconds() is None:
        return
    now = datetime.now(timezone.utc)
    try:
        deleted = (
            db.query(ProductSearchCache)
            .filter(ProductSearchCache.expires_at.isnot(None), ProductSearchCache.expires_at < now)
            .delete(synchronize_session=False)
        )
        if deleted:
            db.commit()
    except Exception:
        db.rollback()


def set_cached_result(
    db: Session,
    cache_key: str,
    response: Dict[str, Any],
    *,
    norm_q: Optional[str] = None,
    query_payload: Optional[Dict[str, Any]] = None,
    ttl_seconds: Optional[int] = None,
) -> None:
    if random.random() < 0.08:
        _prune_expired(db)

    ttl = ttl_seconds if ttl_seconds is not None else _configured_ttl_seconds()
    expires = None if ttl is None else datetime.now(timezone.utc) + timedelta(seconds=int(ttl))
    body = json.dumps(response, ensure_ascii=False, default=str)
    nq = (norm_q or hint_from_cached_json(body) or "").strip()[:500] or None
    query_json = (
        json.dumps(query_payload, sort_keys=True, ensure_ascii=False)
        if query_payload
        else None
    )
    row = db.query(ProductSearchCache).filter(ProductSearchCache.cache_key == cache_key).first()
    try:
        if row:
            row.response_json = body
            row.expires_at = expires
            if nq:
                row.norm_q = nq
            if query_json:
                row.cache_query_json = query_json
        else:
            db.add(
                ProductSearchCache(
                    cache_key=cache_key,
                    response_json=body,
                    expires_at=expires,
                    norm_q=nq,
                    cache_query_json=query_json,
                )
            )
        db.commit()
    except Exception:
        db.rollback()


def count_cache_by_state(db: Session) -> Tuple[int, int, int]:
    """(tổng, còn hiệu lực, hết hạn TTL)."""
    now = datetime.now(timezone.utc)
    total = int(db.query(func.count(ProductSearchCache.cache_key)).scalar() or 0)
    active = int(
        db.query(func.count(ProductSearchCache.cache_key))
        .filter(_cache_is_active_filter(now))
        .scalar()
        or 0
    )
    expired = int(
        db.query(func.count(ProductSearchCache.cache_key))
        .filter(ProductSearchCache.expires_at.isnot(None), ProductSearchCache.expires_at <= now)
        .scalar()
        or 0
    )
    return total, active, expired


def list_cache_rows_admin(db: Session, skip: int, limit: int) -> List[ProductSearchCache]:
    return (
        db.query(ProductSearchCache)
        .order_by(ProductSearchCache.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def clear_product_search_cache(db: Session, *, expired_only: bool) -> int:
    """Xóa hàng cache; trả về số dòng đã xóa."""
    now = datetime.now(timezone.utc)
    q = db.query(ProductSearchCache)
    if expired_only:
        q = q.filter(ProductSearchCache.expires_at.isnot(None), ProductSearchCache.expires_at <= now)
    deleted = q.delete(synchronize_session=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return int(deleted or 0)


def hint_from_cached_json(response_json: str) -> Optional[str]:
    try:
        d = json.loads(response_json)
        if isinstance(d, dict):
            h = d.get("normalized_query") or d.get("applied_query")
            if h and str(h).strip():
                return str(h).strip()[:500]
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _norm_q_for_row(row: ProductSearchCache) -> Optional[str]:
    nq = (getattr(row, "norm_q", None) or "").strip()
    if nq:
        return nq
    return hint_from_cached_json(row.response_json or "")


def _query_payload_for_row(row: ProductSearchCache) -> Optional[Dict[str, Any]]:
    raw = (getattr(row, "cache_query_json", None) or "").strip()
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    nq = _norm_q_for_row(row)
    if not nq:
        return None

    skip = 0
    limit = 48
    sort = "id_desc"
    try:
        cached = json.loads(row.response_json or "{}")
        if isinstance(cached, dict):
            size = int(cached.get("size") or 48)
            page = int(cached.get("page") or 1)
            limit = max(1, size)
            skip = max(0, (page - 1) * limit)
            sort = str(cached.get("sort") or "id_desc").strip() or "id_desc"
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    return build_cache_query_payload(
        norm_q=nq,
        skip=skip,
        limit=limit,
        category=None,
        subcategory=None,
        sub_subcategory=None,
        shop_name=None,
        shop_id=None,
        style=None,
        shop_name_chinese=None,
        chinese_name=None,
        pro_lower_price=None,
        pro_high_price=None,
        min_price=None,
        max_price=None,
        is_active=True,
        sort=sort,
    )


def _payload_to_get_products_kwargs(payload: Dict[str, Any]) -> Dict[str, Any]:
    def _opt_str(key: str) -> Optional[str]:
        v = (payload.get(key) or "").strip()
        return v or None

    def _opt_float(key: str) -> Optional[float]:
        v = payload.get(key)
        if v == "" or v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    from app.crud import product as product_crud

    q = (payload.get("q") or "").strip()
    is_active = payload.get("ia")
    return {
        "skip": int(payload.get("sk") or 0),
        "limit": int(payload.get("li") or 48),
        "category": _opt_str("c1"),
        "subcategory": _opt_str("c2"),
        "sub_subcategory": _opt_str("c3"),
        "shop_name": _opt_str("sn"),
        "shop_id": _opt_str("sid"),
        "style": _opt_str("st"),
        "shop_name_chinese": _opt_str("stc"),
        "chinese_name": _opt_str("cn"),
        "pro_lower_price": _opt_str("pl"),
        "pro_high_price": _opt_str("ph"),
        "min_price": _opt_float("min"),
        "max_price": _opt_float("max"),
        "is_active": True if is_active is not False else False,
        "q": q or None,
        "sort": product_crud.normalize_product_list_sort(str(payload.get("sort") or "id_desc")),
        "filter_size": _opt_str("sz"),
        "filter_color": _opt_str("cl"),
        "filter_style_tag": _opt_str("stylet"),
    }


def rebuild_search_cache_response(db: Session, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Chạy lại GET /products/?q=... và serialize — dùng khi làm mới cache."""
    from app.crud import product as product_crud

    kwargs = _payload_to_get_products_kwargs(payload)
    result = product_crud.get_products(db, **kwargs)
    if not isinstance(result, dict):
        return None
    if result.get("redirect_path") or result.get("error"):
        return None
    if "products" in result:
        from app.api.endpoints.products import _serialize_products_for_api

        result["products"] = _serialize_products_for_api(
            db,
            result["products"],
            user=None,
            include_warehouse_clearance=True,
        )
    return result


def _refresh_cache_row(db: Session, row: ProductSearchCache) -> bool:
    payload = _query_payload_for_row(row)
    if not payload:
        return False
    refreshed = rebuild_search_cache_response(db, payload)
    if refreshed is None:
        return False
    nq = (payload.get("q") or _norm_q_for_row(row) or "").strip() or None
    set_cached_result(
        db,
        row.cache_key,
        refreshed,
        norm_q=nq,
        query_payload=payload,
    )
    return True


def refresh_caches_for_product_states(db: Session, *product_states: Any) -> int:
    """
    Làm mới cache JSON khi SP thêm/xóa khớp từ khóa (cùng logic product_matches_search_keyword).
    Chỉ các dòng cache liên quan — không đụng từ khóa khác.
    """
    from app.services.listing_facet_cache import product_matches_search_keyword

    states = [p for p in product_states if p is not None]
    if not states:
        return 0

    rows = db.query(ProductSearchCache).all()
    refreshed = 0
    for row in rows:
        keyword = _norm_q_for_row(row)
        if not keyword:
            continue
        if not any(product_matches_search_keyword(state, keyword) for state in states):
            continue
        try:
            if _refresh_cache_row(db, row):
                refreshed += 1
        except Exception:
            logger.exception(
                "product_search_cache: refresh failed for key=%s",
                row.cache_key,
            )

    if refreshed:
        logger.info(
            "product_search_cache: refreshed %s row(s) after product add/delete",
            refreshed,
        )
    return refreshed


def refresh_all_caches(db: Session) -> int:
    """Bulk import — làm mới toàn bộ cache tìm kiếm đang lưu."""
    rows = db.query(ProductSearchCache).all()
    refreshed = 0
    for row in rows:
        try:
            if _refresh_cache_row(db, row):
                refreshed += 1
        except Exception:
            logger.exception(
                "product_search_cache: refresh_all failed for key=%s",
                row.cache_key,
            )
    if refreshed:
        logger.info("product_search_cache: refreshed all %s row(s)", refreshed)
    return refreshed


def schedule_refresh_caches_for_product_states(*product_states: Any) -> None:
    """Làm mới cache nền — tránh chặn API create/delete khi query search nặng."""
    states = [p for p in product_states if p is not None]
    if not states:
        return

    def _run() -> None:
        from app.db.session import SessionLocal

        db_bg = SessionLocal()
        try:
            refresh_caches_for_product_states(db_bg, *states)
        except Exception as exc:
            logger.warning("product_search_cache: background refresh failed: %s", exc)
        finally:
            db_bg.close()

    threading.Thread(
        target=_run,
        name="product-search-cache-refresh",
        daemon=True,
    ).start()


# Giữ tên cũ — hành vi là refresh, không xóa.
def invalidate_caches_for_product_states(db: Session, *product_states: Any) -> int:
    return refresh_caches_for_product_states(db, *product_states)


def invalidate_all_caches(db: Session) -> int:
    return refresh_all_caches(db)
