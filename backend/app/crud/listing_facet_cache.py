"""CRUD listing_facet_cache."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.listing_facet_cache import ListingFacetCache

SCOPE_CATEGORY_L1 = "category_l1"
SCOPE_CATEGORY_L2 = "category_l2"
SCOPE_CATEGORY_L3 = "category_l3"
SCOPE_SEARCH_Q = "search_q"
SCOPE_SEO_CLUSTER = "seo_cluster"

ALL_SCOPE_TYPES = (
    SCOPE_CATEGORY_L1,
    SCOPE_CATEGORY_L2,
    SCOPE_CATEGORY_L3,
    SCOPE_SEARCH_Q,
    SCOPE_SEO_CLUSTER,
)


def get_by_scope(db: Session, scope_type: str, scope_key: str) -> Optional[ListingFacetCache]:
    return (
        db.query(ListingFacetCache)
        .filter(
            ListingFacetCache.scope_type == scope_type,
            ListingFacetCache.scope_key == scope_key,
        )
        .first()
    )


def get_by_id(db: Session, row_id: int) -> Optional[ListingFacetCache]:
    return db.query(ListingFacetCache).filter(ListingFacetCache.id == row_id).first()


def row_to_facets(row: ListingFacetCache) -> Dict[str, Any]:
    return {
        "sizes": list(row.sizes_json or []),
        "colors": list(row.colors_json or []),
        "style_tags": list(row.style_tags_json or []),
        "price_min": row.price_min,
        "price_max": row.price_max,
    }


def upsert_facet_cache(
    db: Session,
    *,
    scope_type: str,
    scope_key: str,
    display_label: Optional[str],
    facets: Dict[str, Any],
    product_count: int,
    is_manual: bool = False,
) -> ListingFacetCache:
    row = get_by_scope(db, scope_type, scope_key)
    payload = {
        "sizes_json": list(facets.get("sizes") or []),
        "colors_json": list(facets.get("colors") or []),
        "style_tags_json": list(facets.get("style_tags") or []),
        "price_min": facets.get("price_min"),
        "price_max": facets.get("price_max"),
        "product_count": int(product_count or 0),
        "is_stale": False,
        "updated_at": datetime.now(timezone.utc),
    }
    if row:
        for k, v in payload.items():
            setattr(row, k, v)
        if display_label:
            row.display_label = display_label
        if is_manual:
            row.is_manual = True
    else:
        row = ListingFacetCache(
            scope_type=scope_type,
            scope_key=scope_key,
            display_label=display_label,
            is_manual=is_manual,
            is_enabled=True,
            **payload,
        )
        db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return row


def mark_stale_by_types(db: Session, scope_types: Tuple[str, ...]) -> int:
    if not scope_types:
        return 0
    updated = (
        db.query(ListingFacetCache)
        .filter(ListingFacetCache.scope_type.in_(scope_types))
        .update({ListingFacetCache.is_stale: True}, synchronize_session=False)
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return int(updated or 0)


def mark_stale_for_seo_clusters(db: Session, cluster_slugs: List[str]) -> int:
    if not cluster_slugs:
        return 0
    keys = [s.strip().lower() for s in cluster_slugs if s and s.strip()]
    if not keys:
        return 0
    updated = (
        db.query(ListingFacetCache)
        .filter(
            ListingFacetCache.scope_type == SCOPE_SEO_CLUSTER,
            ListingFacetCache.scope_key.in_(keys),
        )
        .update({ListingFacetCache.is_stale: True}, synchronize_session=False)
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return int(updated or 0)


def delete_row(db: Session, row_id: int) -> bool:
    row = get_by_id(db, row_id)
    if not row:
        return False
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def clear_by_scope_type(db: Session, scope_type: Optional[str] = None) -> int:
    q = db.query(ListingFacetCache)
    if scope_type:
        q = q.filter(ListingFacetCache.scope_type == scope_type)
    deleted = q.delete(synchronize_session=False)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return int(deleted or 0)


def count_by_scope_type(db: Session) -> Dict[str, int]:
    rows = (
        db.query(ListingFacetCache.scope_type, func.count(ListingFacetCache.id))
        .group_by(ListingFacetCache.scope_type)
        .all()
    )
    out = {t: 0 for t in ALL_SCOPE_TYPES}
    for scope_type, cnt in rows:
        out[str(scope_type)] = int(cnt or 0)
    return out


def list_rows_admin(
    db: Session,
    *,
    scope_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[int, List[ListingFacetCache]]:
    q = db.query(ListingFacetCache)
    if scope_type:
        q = q.filter(ListingFacetCache.scope_type == scope_type)
    total = int(q.count())
    rows = (
        q.order_by(
            ListingFacetCache.updated_at.desc().nullslast(),
            ListingFacetCache.id.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def set_enabled(db: Session, row_id: int, enabled: bool) -> Optional[ListingFacetCache]:
    row = get_by_id(db, row_id)
    if not row:
        return None
    row.is_enabled = bool(enabled)
    row.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return row
