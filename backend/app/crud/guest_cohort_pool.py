"""
Pool cohort cho khách CHƯA đăng nhập, theo giới tính (+ năm sinh tùy chọn) tự khai qua
`GuestProfileHint` — mirror `app.crud.cohort_view_pool_cache` (dành cho user thật) nhưng
cache theo NHÓM nhân khẩu học (`bucket_key`) thay vì theo từng user, vì nhiều guest cùng
bucket dùng chung 1 pool đã tính.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.crud import guest_behavior as guest_behavior_crud
from app.crud.cohort_view_pool_cache import (
    COHORT_VIEW_POOL_CACHE_SIZE,
    COHORT_VIEW_POOL_CACHE_TTL_HOURS,
    _hydrate_products,
    _peer_ids_same_gender,
    _peer_ids_same_year_gender,
    _product_ids_from_peer_recent_views,
)
from app.models.guest_cohort_view_pool_cache import GuestCohortPoolCache
from app.models.product import Product

# Sentinel "user_id" khi tái dùng các hàm tính peer viết cho User thật — không guest nào
# trùng id này nên coi như "không loại trừ ai" (peer query dùng `User.id != user_id`).
_GUEST_SENTINEL_USER_ID = -1

VALID_GENDERS = ("male", "female")


def guest_cohort_bucket_key(gender: str, birth_year: Optional[int]) -> str:
    g = (gender or "").strip().lower()
    if birth_year:
        return f"{g}:{int(birth_year)}"
    return f"{g}:_any"


def _cache_is_stale(computed_at) -> bool:
    if not computed_at:
        return True
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - computed_at
    return age > timedelta(hours=COHORT_VIEW_POOL_CACHE_TTL_HOURS)


def get_cached_guest_cohort_pool(db: Session, bucket_key: str) -> Optional[Tuple[List[int], str]]:
    row = (
        db.query(GuestCohortPoolCache)
        .filter(GuestCohortPoolCache.bucket_key == bucket_key)
        .first()
    )
    if not row or _cache_is_stale(row.computed_at):
        return None
    ids = row.product_ids if isinstance(row.product_ids, list) else []
    return list(ids), str(row.cohort_mode or "gender_peers")


def save_guest_cohort_pool_cache(
    db: Session, bucket_key: str, product_ids: List[int], cohort_mode: str
) -> None:
    row = (
        db.query(GuestCohortPoolCache)
        .filter(GuestCohortPoolCache.bucket_key == bucket_key)
        .first()
    )
    if row:
        row.cohort_mode = cohort_mode
        row.product_ids = product_ids
    else:
        row = GuestCohortPoolCache(
            bucket_key=bucket_key, cohort_mode=cohort_mode, product_ids=product_ids
        )
        db.add(row)
    db.commit()


def build_guest_cohort_pool(
    db: Session, gender: str, birth_year: Optional[int]
) -> Tuple[List[int], str]:
    """Query nặng: lấy tối đa 100 product_id xem gần nhất từ peer thật cùng giới/năm sinh."""
    pool_size = COHORT_VIEW_POOL_CACHE_SIZE

    if birth_year:
        same_year_gender_ids = _peer_ids_same_year_gender(
            db, _GUEST_SENTINEL_USER_ID, gender, birth_year
        )
        product_ids = _product_ids_from_peer_recent_views(
            db, _GUEST_SENTINEL_USER_ID, same_year_gender_ids, pool_size=pool_size
        )
        if product_ids:
            return product_ids, "exact_cohort"

    gender_peer_ids = _peer_ids_same_gender(db, _GUEST_SENTINEL_USER_ID, gender)
    product_ids = _product_ids_from_peer_recent_views(
        db, _GUEST_SENTINEL_USER_ID, gender_peer_ids, pool_size=pool_size
    )
    if product_ids:
        return product_ids, "gender_peers"

    return [], "popular_fallback"


def get_or_build_guest_cohort_pool(
    db: Session, gender: str, birth_year: Optional[int]
) -> Tuple[List[int], str]:
    bucket_key = guest_cohort_bucket_key(gender, birth_year)
    cached = get_cached_guest_cohort_pool(db, bucket_key)
    if cached is not None:
        return cached
    product_ids, cohort_mode = build_guest_cohort_pool(db, gender, birth_year)
    save_guest_cohort_pool_cache(db, bucket_key, product_ids, cohort_mode)
    return product_ids, cohort_mode


def sample_guest_cohort_products_from_pool(
    db: Session,
    *,
    session_id: str,
    gender: str,
    birth_year: Optional[int] = None,
    limit: int = 24,
) -> Tuple[List[Product], str]:
    """
    Mỗi lần gọi: đọc pool cache theo bucket (hoặc build 1 lần), loại SP guest đã xem
    (session), shuffle, trả tối đa `limit`. Rơi về fallback "phổ biến" khi bucket chưa có
    peer data.
    """
    gender = (gender or "").strip().lower()
    if gender not in VALID_GENDERS:
        return [], "profile_incomplete"

    pool_ids, cohort_mode = get_or_build_guest_cohort_pool(db, gender, birth_year)

    if cohort_mode == "popular_fallback" or not pool_ids:
        from app.crud.popular_fallback import get_popular_fallback_products
        from app.crud.user import get_recent_view_product_ids

        exclude_ids = get_recent_view_product_ids(db, guest_session_id=session_id, limit=40)
        popular = get_popular_fallback_products(db, exclude_product_ids=exclude_ids, limit=limit)
        return popular, "popular_fallback"

    self_viewed_ids = set(
        guest_behavior_crud.recent_guest_view_product_ids(db, session_id, limit=200)
    )
    filtered = [pid for pid in pool_ids if pid not in self_viewed_ids]
    if not filtered:
        return [], cohort_mode
    shuffled = filtered.copy()
    random.shuffle(shuffled)
    return _hydrate_products(db, shuffled, limit), cohort_mode
