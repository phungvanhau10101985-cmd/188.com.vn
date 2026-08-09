"""
Nguồn dữ liệu thô (same-shop + cohort/fallback) cho khối gợi ý trang chủ
«CÓ THỂ BẠN THÍCH» — dùng chung cho cả đường tính tươi
(`app.crud.home_recommendation_block.build_home_recommendation_block_rows`) và
tính nền (`app.crud.home_recommendation_snapshot.build_home_recommendation_snapshot`),
tránh 2 nơi tự viết lại logic same-shop/cohort/fallback (dễ lệch hành vi).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.crud.guest_behavior import get_guest_profile_hint
from app.crud.guest_cohort_pool import sample_guest_cohort_products_from_pool
from app.crud.popular_fallback import get_popular_fallback_products
from app.crud.user import (
    get_products_same_shop_as_recent_views,
    get_products_viewed_by_same_age_gender,
    get_recent_view_product_ids,
)
from app.db.session import SessionLocal
from app.models.product import Product

logger = logging.getLogger(__name__)

HOME_RECOMMENDATION_SHOP_LIMIT_DEFAULT = 24
HOME_RECOMMENDATION_COHORT_LIMIT_DEFAULT = 30


def _fetch_same_shop_thread(
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    limit: int,
) -> Tuple[List[Product], int, Optional[int]]:
    db = SessionLocal()
    try:
        return get_products_same_shop_as_recent_views(
            db,
            user_id=user_id,
            limit=limit,
            offset=0,
            seed=None,
            guest_session_id=guest_session_id,
        )
    finally:
        db.close()


def _fetch_cohort_thread(*, user_id: int, limit: int) -> Tuple[List[Product], str]:
    db = SessionLocal()
    try:
        return get_products_viewed_by_same_age_gender(db, user_id, limit=limit)
    finally:
        db.close()


def _resolve_guest_cohort_or_fallback(
    db: Session,
    *,
    guest_session_id: str,
    shop_products: List[Product],
    limit: int,
) -> Tuple[List[Product], str]:
    """
    Guest: ưu tiên cohort theo giới tính/năm sinh tự khai (nếu đã chọn), sau đó rơi về
    fallback "phổ biến" khi không có same-shop products (chưa xem gì, hoặc đã xem nhưng
    toàn bộ SP thiếu `shop_name_chinese` nên same-shop rỗng). Không rơi về fallback khi đã có
    same-shop products và không có hint — tránh lặp lại nội dung đã hiển thị.
    """
    try:
        hint = get_guest_profile_hint(db, guest_session_id)
    except Exception:
        logger.exception("home_recommendation_sources: guest profile hint lookup failed")
        hint = None

    if hint is not None and hint.gender:
        try:
            cohort_products, cohort_mode = sample_guest_cohort_products_from_pool(
                db,
                session_id=guest_session_id,
                gender=hint.gender,
                birth_year=hint.birth_year,
                limit=limit,
            )
            if cohort_products:
                return cohort_products, cohort_mode
            if shop_products:
                return [], cohort_mode
            # Bucket của hint chưa có peer data lẫn fallback (hiếm) — rơi tiếp xuống dưới.
        except Exception:
            logger.exception("home_recommendation_sources: guest cohort pool failed")

    if shop_products:
        return [], "requires_login"

    try:
        exclude_ids = get_recent_view_product_ids(
            db, guest_session_id=guest_session_id, limit=40
        )
        fallback = get_popular_fallback_products(
            db, exclude_product_ids=exclude_ids, limit=limit
        )
    except Exception:
        logger.exception("home_recommendation_sources: guest popular fallback failed")
        return [], "requires_login"

    if not fallback:
        return [], "requires_login"
    return fallback, "popular_fallback"


def resolve_recommendation_sources(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    shop_limit: int = HOME_RECOMMENDATION_SHOP_LIMIT_DEFAULT,
    cohort_limit: int = HOME_RECOMMENDATION_COHORT_LIMIT_DEFAULT,
) -> Dict[str, Any]:
    """
    Lấy ORM same-shop + cohort/fallback song song (2 session) cho 1 identity
    (user hoặc guest) — CHƯA mix/serialize.
    """
    shop_limit = max(1, min(shop_limit, 60))
    cohort_limit = max(1, min(cohort_limit, 100))
    sid = (guest_session_id or "").strip() or None

    shop_products: List[Product] = []
    shop_total = 0
    shop_seed: Optional[int] = None
    cohort_products: List[Product] = []
    cohort_mode = "requires_login"

    if user_id is not None:
        with ThreadPoolExecutor(max_workers=2) as pool:
            shop_future = pool.submit(
                _fetch_same_shop_thread,
                user_id=user_id,
                guest_session_id=None,
                limit=shop_limit,
            )
            cohort_future = pool.submit(
                _fetch_cohort_thread,
                user_id=user_id,
                limit=cohort_limit,
            )
            try:
                shop_products, shop_total, shop_seed = shop_future.result()
            except Exception:
                logger.exception("home_recommendation_sources: same-shop fetch failed")
                shop_products, shop_total, shop_seed = [], 0, None
            try:
                cohort_products, cohort_mode = cohort_future.result()
            except Exception:
                logger.exception("home_recommendation_sources: cohort fetch failed")
                cohort_products, cohort_mode = [], "popular_fallback"
    elif sid:
        try:
            shop_products, shop_total, shop_seed = _fetch_same_shop_thread(
                user_id=None,
                guest_session_id=sid,
                limit=shop_limit,
            )
        except Exception:
            logger.exception("home_recommendation_sources: guest same-shop fetch failed")
            shop_products, shop_total, shop_seed = [], 0, None

        cohort_products, cohort_mode = _resolve_guest_cohort_or_fallback(
            db,
            guest_session_id=sid,
            shop_products=shop_products,
            limit=cohort_limit,
        )
    else:
        shop_products, shop_total, shop_seed = [], 0, None

    return {
        "shop_products": shop_products,
        "shop_total": shop_total,
        "shop_seed": shop_seed,
        "cohort_products": cohort_products,
        "cohort_mode": cohort_mode,
    }
