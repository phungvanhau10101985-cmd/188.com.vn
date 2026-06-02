"""Build / lưu snapshot trang chủ (khối gợi ý + lưới cá nhân hóa trang 1)."""

from __future__ import annotations

import random
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.crud.personalized_feed import get_personalized_home_products
from app.crud.user import (
    SAME_AGE_GENDER_RECENT_VIEW_POOL,
    get_products_same_shop_as_recent_views,
    get_products_viewed_by_same_age_gender,
)
from app.models.home_recommendation_snapshot import UserHomeRecommendationSnapshot
from app.models.user import User

HOME_MIX_INITIAL_LIMIT = 24
HOME_MAIN_FEED_LIMIT = 48


def home_snapshot_version_key(user: User) -> str:
    dob = ""
    if user.date_of_birth:
        dob = user.date_of_birth.isoformat() if isinstance(user.date_of_birth, date) else str(user.date_of_birth)
    return f"{user.id}:{user.gender or ''}:{dob}"


def _dedupe_products_by_id(products: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for p in products:
        pid = getattr(p, "id", None)
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        out.append(p)
    return out


def _next_seeded_uint32(state: int) -> int:
    return ((state * 1664525) + 1013904223) & 0xFFFFFFFF


def mix_shop_and_cohort_products(
    shop_products: List[Any],
    cohort_products: List[Any],
    mix_seed: Optional[int],
) -> List[Any]:
    shop = _dedupe_products_by_id(shop_products)
    shop_ids = {getattr(p, "id", None) for p in shop}
    cohort_only = [p for p in _dedupe_products_by_id(cohort_products) if getattr(p, "id", None) not in shop_ids]
    if not cohort_only:
        return shop
    rng = int(mix_seed or 1) & 0xFFFFFFFF
    mixed = list(shop)
    for product in cohort_only:
        rng = _next_seeded_uint32(rng)
        insert_at = rng % (len(mixed) + 1)
        mixed.insert(insert_at, product)
    return mixed


def infer_same_shop_load_more_available(
    loaded_count: int,
    last_batch_size: int,
    page_limit: int,
    reported_total: int,
) -> bool:
    if loaded_count <= 0 or last_batch_size <= 0:
        return False
    reported = max(0, reported_total)
    if reported > loaded_count:
        return True
    if last_batch_size >= page_limit and reported == 0:
        return True
    return False


def cohort_badge_product_ids(shop_products: List[dict], cohort_products: List[dict]) -> List[int]:
    shop_ids = {p.get("id") for p in shop_products if p.get("id") is not None}
    return [int(p["id"]) for p in cohort_products if p.get("id") is not None and p["id"] not in shop_ids]


def get_user_home_snapshot(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    row = db.query(UserHomeRecommendationSnapshot).filter(
        UserHomeRecommendationSnapshot.user_id == user_id
    ).first()
    if not row or not row.payload:
        return None
    return {
        "version_key": row.version_key,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
        "snapshot": row.payload,
    }


def build_home_recommendation_snapshot(
    db: Session,
    user: User,
    *,
    serialize_products,
) -> Dict[str, Any]:
    """
    Tính phiên mới: same-shop (24) + cohort (30) + mix + home-feed (48).
    `serialize_products(db, products, user)` → list[dict] API-safe.
    """
    uid = user.id
    shop_products, shop_total, shop_seed = get_products_same_shop_as_recent_views(
        db, user_id=uid, limit=HOME_MIX_INITIAL_LIMIT, offset=0, seed=None
    )
    shop_list = list(shop_products or [])
    shop_serialized = serialize_products(db, shop_list, user)
    loaded = len(shop_list)
    reported = max(int(shop_total or 0), loaded)
    can_load_more = infer_same_shop_load_more_available(
        loaded, loaded, HOME_MIX_INITIAL_LIMIT, reported
    )

    cohort_products: List[Any] = []
    cohort_mode = "requires_login"
    if user.date_of_birth and user.gender:
        cohort_products, cohort_mode = get_products_viewed_by_same_age_gender(
            db, uid, limit=SAME_AGE_GENDER_RECENT_VIEW_POOL
        )
    cohort_serialized = serialize_products(db, list(cohort_products or []), user)

    mixed_rows = mix_shop_and_cohort_products(shop_list, list(cohort_products or []), shop_seed)
    mixed_serialized = serialize_products(db, mixed_rows, user)
    badge_ids = cohort_badge_product_ids(shop_serialized, cohort_serialized)

    main_products, main_total, main_personalized = get_personalized_home_products(
        db,
        user_id=uid,
        guest_session_id=None,
        skip=0,
        limit=HOME_MAIN_FEED_LIMIT,
    )
    main_serialized = serialize_products(db, list(main_products or []), user)

    recommendation = {
        "same_shop_products": shop_serialized,
        "same_shop_total": reported,
        "same_shop_seed": shop_seed,
        "same_shop_can_load_more": can_load_more,
        "same_age_gender_products": cohort_serialized,
        "same_age_gender_cohort_mode": cohort_mode,
        "mixed_recommendation_products": mixed_serialized,
        "cohort_badge_product_ids": badge_ids,
    }
    main_feed = {
        "products": main_serialized,
        "total": int(main_total or 0),
        "personalized": bool(main_personalized),
        "page": 1,
        "size": HOME_MAIN_FEED_LIMIT,
    }
    version_key = home_snapshot_version_key(user)
    payload = {
        "main_feed": main_feed,
        "recommendation": recommendation,
    }
    return {
        "version_key": version_key,
        "computed_at": datetime.utcnow().isoformat() + "Z",
        "snapshot": payload,
    }


def save_user_home_snapshot(db: Session, user_id: int, version_key: str, payload: Dict[str, Any]) -> None:
    row = db.query(UserHomeRecommendationSnapshot).filter(
        UserHomeRecommendationSnapshot.user_id == user_id
    ).first()
    if row:
        row.version_key = version_key
        row.payload = payload
    else:
        row = UserHomeRecommendationSnapshot(
            user_id=user_id,
            version_key=version_key,
            payload=payload,
        )
        db.add(row)
    db.commit()


def build_and_save_user_home_snapshot(
    db: Session,
    user: User,
    *,
    serialize_products,
) -> Dict[str, Any]:
    built = build_home_recommendation_snapshot(db, user, serialize_products=serialize_products)
    save_user_home_snapshot(
        db,
        user.id,
        built["version_key"],
        built["snapshot"],
    )
    return built
