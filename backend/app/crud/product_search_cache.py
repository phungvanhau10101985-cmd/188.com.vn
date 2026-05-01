"""
Đọc/ghi cache JSON kết quả GET /products/?q=... (payload trả về client sau khi serialize SP).
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product_search_cache import ProductSearchCache

# Đồng bộ mức chờ đổi kho hợp lý với frontend session cache (~5 phút).
DEFAULT_TTL_SECONDS = 300


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
    pro_lower_price: Optional[str],
    pro_high_price: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    is_active: Optional[bool],
) -> str:
    payload = {
        "q": norm_q or "",
        "sk": int(skip),
        "li": int(limit),
        "c1": (category or "").strip(),
        "c2": (subcategory or "").strip(),
        "c3": (sub_subcategory or "").strip(),
        "sn": (shop_name or "").strip(),
        "sid": (shop_id or "").strip(),
        "pl": (pro_lower_price or "").strip(),
        "ph": (pro_high_price or "").strip(),
        "min": "" if min_price is None else float(min_price),
        "max": "" if max_price is None else float(max_price),
        "ia": True if is_active is not False else False,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def get_cached_result(db: Session, cache_key: str) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    row = (
        db.query(ProductSearchCache)
        .filter(ProductSearchCache.cache_key == cache_key, ProductSearchCache.expires_at > now)
        .first()
    )
    if not row:
        return None
    try:
        return json.loads(row.response_json)
    except json.JSONDecodeError:
        return None


def _prune_expired(db: Session) -> None:
    now = datetime.now(timezone.utc)
    try:
        deleted = (
            db.query(ProductSearchCache)
            .filter(ProductSearchCache.expires_at < now)
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
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> None:
    if random.random() < 0.08:
        _prune_expired(db)

    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    body = json.dumps(response, ensure_ascii=False, default=str)
    row = db.query(ProductSearchCache).filter(ProductSearchCache.cache_key == cache_key).first()
    try:
        if row:
            row.response_json = body
            row.expires_at = expires
        else:
            db.add(
                ProductSearchCache(
                    cache_key=cache_key,
                    response_json=body,
                    expires_at=expires,
                )
            )
        db.commit()
    except Exception:
        db.rollback()


def count_cache_by_state(db: Session) -> Tuple[int, int, int]:
    """(tổng, còn hạn, hết hạn)."""
    now = datetime.now(timezone.utc)
    total = int(db.query(func.count(ProductSearchCache.cache_key)).scalar() or 0)
    active = int(
        db.query(func.count(ProductSearchCache.cache_key))
        .filter(ProductSearchCache.expires_at > now)
        .scalar()
        or 0
    )
    expired = int(
        db.query(func.count(ProductSearchCache.cache_key))
        .filter(ProductSearchCache.expires_at <= now)
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
        q = q.filter(ProductSearchCache.expires_at <= now)
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
