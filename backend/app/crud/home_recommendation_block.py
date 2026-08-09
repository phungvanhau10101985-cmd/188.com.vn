"""Khối gợi ý trang chủ «CÓ THỂ BẠN THÍCH» — same-shop + cohort trong một lần build."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.crud.home_recommendation_snapshot import (
    cohort_badge_product_ids,
    infer_same_shop_load_more_available,
    mix_shop_and_cohort_products,
)
from app.crud.home_recommendation_sources import (
    HOME_RECOMMENDATION_COHORT_LIMIT_DEFAULT,
    HOME_RECOMMENDATION_SHOP_LIMIT_DEFAULT,
    resolve_recommendation_sources,
)
from app.models.product import Product

# Re-export để giữ tương thích với các import cũ (app.crud.home_recommendation_block.HOME_RECOMMENDATION_*).
__all__ = [
    "HOME_RECOMMENDATION_SHOP_LIMIT_DEFAULT",
    "HOME_RECOMMENDATION_COHORT_LIMIT_DEFAULT",
    "build_home_recommendation_block_rows",
    "serialize_home_recommendation_block",
]


def build_home_recommendation_block_rows(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    shop_limit: int = HOME_RECOMMENDATION_SHOP_LIMIT_DEFAULT,
    cohort_limit: int = HOME_RECOMMENDATION_COHORT_LIMIT_DEFAULT,
) -> Dict[str, Any]:
    """
    Lấy ORM same-shop + cohort song song (2 session), trộn lưới — chưa serialize JSON.
    `db` chỉ dùng cho phần fallback/cohort-guest (chạy trên session của request);
    same-shop/cohort của user vẫn fetch song song qua session riêng trong thread.
    """
    sources = resolve_recommendation_sources(
        db,
        user_id=user_id,
        guest_session_id=guest_session_id,
        shop_limit=shop_limit,
        cohort_limit=cohort_limit,
    )

    shop_products = sources["shop_products"]
    shop_total = sources["shop_total"]
    shop_seed = sources["shop_seed"]
    cohort_products = sources["cohort_products"]
    cohort_mode = sources["cohort_mode"]

    shop_list = list(shop_products or [])
    cohort_list = list(cohort_products or [])
    loaded = len(shop_list)
    reported_total = max(int(shop_total or 0), loaded)
    can_load_more = infer_same_shop_load_more_available(
        loaded, loaded, shop_limit, reported_total
    )

    mixed_rows = mix_shop_and_cohort_products(shop_list, cohort_list, shop_seed)

    return {
        "same_shop_products": shop_list,
        "same_shop_total": reported_total,
        "same_shop_seed": shop_seed,
        "same_shop_can_load_more": can_load_more,
        "same_age_gender_products": cohort_list,
        "same_age_gender_cohort_mode": cohort_mode,
        "mixed_recommendation_products": mixed_rows,
        "cohort_badge_product_ids": cohort_badge_product_ids(
            [{"id": p.id} for p in shop_list],
            [{"id": p.id} for p in cohort_list],
        ),
    }


def serialize_home_recommendation_block(
    db: Session,
    block: Dict[str, Any],
    *,
    serialize_products: Callable[..., List[dict]],
    user: Any = None,
) -> Dict[str, Any]:
    """Một lần resolve sale calendar; mỗi SP chỉ serialize một lần."""
    shop_rows = list(block.get("same_shop_products") or [])
    cohort_rows = list(block.get("same_age_gender_products") or [])
    mixed_rows = list(block.get("mixed_recommendation_products") or [])

    unique_rows: List[Product] = []
    seen_ids: set[int] = set()
    for product in shop_rows + cohort_rows + mixed_rows:
        pid = getattr(product, "id", None)
        if pid is None or pid in seen_ids:
            continue
        seen_ids.add(pid)
        unique_rows.append(product)

    serialized_unique = serialize_products(db, unique_rows, user)
    by_id = {int(item["id"]): item for item in serialized_unique if item.get("id") is not None}

    def _map_rows(rows: List[Product]) -> List[dict]:
        out: List[dict] = []
        for product in rows:
            pid = getattr(product, "id", None)
            if pid is None:
                continue
            mapped = by_id.get(int(pid))
            if mapped is not None:
                out.append(mapped)
        return out

    shop_serialized = _map_rows(shop_rows)
    cohort_serialized = _map_rows(cohort_rows)
    mixed_serialized = _map_rows(mixed_rows)
    badge_ids = cohort_badge_product_ids(shop_serialized, cohort_serialized)

    return {
        "same_shop_products": shop_serialized,
        "same_shop_total": int(block.get("same_shop_total") or 0),
        "same_shop_seed": block.get("same_shop_seed"),
        "same_shop_can_load_more": bool(block.get("same_shop_can_load_more")),
        "same_age_gender_products": cohort_serialized,
        "same_age_gender_cohort_mode": block.get("same_age_gender_cohort_mode") or "requires_login",
        "mixed_recommendation_products": mixed_serialized,
        "cohort_badge_product_ids": badge_ids,
    }
