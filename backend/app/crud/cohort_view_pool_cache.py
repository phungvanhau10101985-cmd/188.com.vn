"""Pool 100 SP nhóm tuổi/giới (cache DB) + sample nhanh mỗi lần gọi API."""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.crud.user import get_user
from app.models.product import Product
from app.models.user import User, UserProductView
from app.models.user_cohort_view_pool_cache import UserCohortViewPoolCache

# Số SP xem gần nhất của nhóm peer lưu vào cache (tính 1 lần, dùng nhiều lần).
COHORT_VIEW_POOL_CACHE_SIZE = 100
# TTL rebuild pool peer từ DB (giờ).
COHORT_VIEW_POOL_CACHE_TTL_HOURS = 6


def cohort_pool_version_key(user: User) -> str:
    dob = ""
    if user.date_of_birth:
        dob = (
            user.date_of_birth.isoformat()
            if isinstance(user.date_of_birth, date)
            else str(user.date_of_birth)
        )
    return f"{user.gender or ''}:{dob}"


def _self_viewed_product_ids_subquery(db: Session, user_id: int):
    return (
        db.query(UserProductView.product_id)
        .filter(UserProductView.user_id == user_id)
        .distinct()
        .subquery()
    )


def _product_ids_from_peer_recent_views(
    db: Session,
    user_id: int,
    peer_ids: List[int],
    *,
    pool_size: int,
) -> List[int]:
    if not peer_ids:
        return []
    peer_ids = [pid for pid in peer_ids if pid != user_id]
    if not peer_ids:
        return []
    self_viewed = _self_viewed_product_ids_subquery(db, user_id)
    rows = (
        db.query(
            UserProductView.product_id,
            func.max(UserProductView.viewed_at).label("last_viewed"),
        )
        .filter(UserProductView.user_id.in_(peer_ids))
        .filter(~UserProductView.product_id.in_(db.query(self_viewed.c.product_id)))
        .group_by(UserProductView.product_id)
        .order_by(func.max(UserProductView.viewed_at).desc())
        .limit(pool_size)
        .all()
    )
    return [r[0] for r in rows]


def _peer_ids_same_year_gender(db: Session, user_id: int, gender: str, birth_year: int) -> List[int]:
    return [
        r[0]
        for r in db.query(User.id)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.id != user_id)
        .filter(User.gender == gender)
        .filter(extract("year", User.date_of_birth) == birth_year)
        .all()
    ]


def _peer_ids_same_gender(db: Session, user_id: int, gender: str) -> List[int]:
    return [
        r[0]
        for r in db.query(User.id)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.id != user_id)
        .filter(User.gender == gender)
        .all()
    ]


def build_cohort_view_pool(db: Session, user_id: int) -> Tuple[List[int], str]:
    """
    Query nặng: lấy tối đa 100 product_id xem gần nhất từ peer (ưu tiên cùng năm sinh + giới).
    """
    user = get_user(db, user_id)
    if not user or not user.date_of_birth or not user.gender:
        return [], "profile_incomplete"

    birth_year = user.date_of_birth.year
    gender = user.gender
    pool_size = COHORT_VIEW_POOL_CACHE_SIZE

    same_year_gender_ids = _peer_ids_same_year_gender(db, user_id, gender, birth_year)
    product_ids = _product_ids_from_peer_recent_views(
        db, user_id, same_year_gender_ids, pool_size=pool_size
    )
    if product_ids:
        return product_ids, "exact_cohort"

    gender_peer_ids = _peer_ids_same_gender(db, user_id, gender)
    product_ids = _product_ids_from_peer_recent_views(
        db, user_id, gender_peer_ids, pool_size=pool_size
    )
    if product_ids:
        return product_ids, "gender_peers"

    return [], "popular_fallback"


def _cache_is_stale(computed_at: Optional[datetime]) -> bool:
    if not computed_at:
        return True
    if computed_at.tzinfo is None:
        computed_at = computed_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - computed_at
    return age > timedelta(hours=COHORT_VIEW_POOL_CACHE_TTL_HOURS)


def get_cached_cohort_pool(db: Session, user_id: int, version_key: str) -> Optional[Tuple[List[int], str]]:
    row = (
        db.query(UserCohortViewPoolCache)
        .filter(UserCohortViewPoolCache.user_id == user_id)
        .first()
    )
    if not row or row.version_key != version_key:
        return None
    if _cache_is_stale(row.computed_at):
        return None
    ids = row.product_ids if isinstance(row.product_ids, list) else []
    return list(ids), str(row.cohort_mode or "exact_cohort")


def save_cohort_view_pool_cache(
    db: Session,
    user_id: int,
    version_key: str,
    product_ids: List[int],
    cohort_mode: str,
) -> None:
    row = (
        db.query(UserCohortViewPoolCache)
        .filter(UserCohortViewPoolCache.user_id == user_id)
        .first()
    )
    if row:
        row.version_key = version_key
        row.cohort_mode = cohort_mode
        row.product_ids = product_ids
    else:
        row = UserCohortViewPoolCache(
            user_id=user_id,
            version_key=version_key,
            cohort_mode=cohort_mode,
            product_ids=product_ids,
        )
        db.add(row)
    db.commit()


def _filter_pool_exclude_self_views(db: Session, user_id: int, product_ids: List[int]) -> List[int]:
    if not product_ids:
        return []
    self_ids = {
        r[0]
        for r in db.query(UserProductView.product_id)
        .filter(UserProductView.user_id == user_id)
        .filter(UserProductView.product_id.in_(product_ids))
        .distinct()
        .all()
    }
    return [pid for pid in product_ids if pid not in self_ids]


def _hydrate_products(db: Session, product_ids: List[int], limit: int) -> List[Product]:
    if not product_ids:
        return []
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    rows = (
        apply_catalog_visibility_filter(
            db.query(Product).filter(Product.id.in_(product_ids), Product.is_active == True)  # noqa: E712
        )
        .all()
    )
    order_map = {pid: i for i, pid in enumerate(product_ids)}
    rows.sort(key=lambda p: order_map.get(p.id, 999))
    return rows[:limit]


def get_or_build_cohort_pool(db: Session, user_id: int) -> Tuple[List[int], str]:
    user = get_user(db, user_id)
    if not user or not user.date_of_birth or not user.gender:
        return [], "profile_incomplete"

    version_key = cohort_pool_version_key(user)
    cached = get_cached_cohort_pool(db, user_id, version_key)
    if cached is not None:
        return cached

    product_ids, cohort_mode = build_cohort_view_pool(db, user_id)
    save_cohort_view_pool_cache(db, user_id, version_key, product_ids, cohort_mode)
    return product_ids, cohort_mode


def sample_cohort_products_from_pool(
    db: Session, user_id: int, limit: int = 24
) -> Tuple[List[Product], str]:
    """
    Mỗi lần gọi: đọc pool cache (hoặc build 1 lần), loại SP user đã xem (mới), shuffle, trả tối đa limit.
    """
    user = get_user(db, user_id)
    if not user or not user.date_of_birth or not user.gender:
        return [], "profile_incomplete"

    pool_ids, cohort_mode = get_or_build_cohort_pool(db, user_id)

    if cohort_mode == "popular_fallback" or not pool_ids:
        self_viewed = _self_viewed_product_ids_subquery(db, user_id)
        from app.services.warehouse_clearance import apply_catalog_visibility_filter

        popular = (
            apply_catalog_visibility_filter(
                db.query(Product)
                .filter(Product.is_active == True)  # noqa: E712
                .filter(~Product.id.in_(db.query(self_viewed.c.product_id)))
            )
            .order_by(Product.purchases.desc().nullslast(), Product.id)
            .limit(limit)
            .all()
        )
        return popular, "popular_fallback"

    filtered = _filter_pool_exclude_self_views(db, user_id, pool_ids)
    if not filtered:
        return [], cohort_mode
    shuffled = filtered.copy()
    random.shuffle(shuffled)
    return _hydrate_products(db, shuffled, limit), cohort_mode
