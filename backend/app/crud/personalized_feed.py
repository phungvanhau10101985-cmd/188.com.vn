"""
Feed trang chủ cá nhân hóa từ lượt xem + yêu thích (đăng nhập hoặc phiên khách).
Không tín hiệu → sắp xếp theo độ phổ biến (purchases).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy import case, or_, and_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func as sql_func

from app.models.product import Product
from app.models.user import UserProductView, UserFavorite
from app.crud.product import category_field_equals_ci
from app.crud import guest_behavior as guest_behavior_crud


def _merge_signal_product_ids(view_ids: List[int], fav_ids: List[int], max_n: int = 40) -> List[int]:
    seen = set()
    out: List[int] = []
    for pid in view_ids + fav_ids:
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        if len(out) >= max_n:
            break
    return out


def _signal_ids_for_user(db: Session, user_id: int) -> List[int]:
    view_rows = (
        db.query(UserProductView.product_id)
        .filter(UserProductView.user_id == user_id)
        .order_by(UserProductView.viewed_at.desc())
        .limit(28)
        .all()
    )
    view_ids = [r[0] for r in view_rows]
    fav_rows = (
        db.query(UserFavorite.product_id)
        .filter(UserFavorite.user_id == user_id)
        .order_by(UserFavorite.created_at.desc())
        .limit(28)
        .all()
    )
    fav_ids = [r[0] for r in fav_rows]
    return _merge_signal_product_ids(view_ids, fav_ids)


def _signal_ids_for_guest(db: Session, guest_session_id: str) -> List[int]:
    sid = (guest_session_id or "").strip()
    if not sid:
        return []
    view_ids = guest_behavior_crud.recent_guest_view_product_ids(db, sid, limit=28)
    fav_ids = guest_behavior_crud.recent_guest_favorite_product_ids(db, sid, limit=28)
    return _merge_signal_product_ids(view_ids, fav_ids)


def _fallback_popularity(db: Session, skip: int, limit: int) -> Tuple[List[Product], int, bool]:
    base = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    total = base.count()
    products = (
        base.order_by(Product.purchases.desc().nullslast(), Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return products, total, False


def get_personalized_home_products(
    db: Session,
    *,
    user_id: Optional[int],
    guest_session_id: Optional[str],
    skip: int = 0,
    limit: int = 48,
) -> Tuple[List[Product], int, bool]:
    """
    Trả về (products, total, personalized).
    personalized=True khi có tín hiệu hành vi và áp xếp hạng tier (danh mục / shop).
    """
    signal_ids: List[int] = []
    if user_id is not None:
        signal_ids = _signal_ids_for_user(db, user_id)
    elif guest_session_id and str(guest_session_id).strip():
        signal_ids = _signal_ids_for_guest(db, str(guest_session_id).strip())

    if not signal_ids:
        return _fallback_popularity(db, skip, limit)

    sig_products = db.query(Product).filter(Product.id.in_(signal_ids)).all()
    if not sig_products:
        return _fallback_popularity(db, skip, limit)

    pair_conditions = []
    seen_pairs = set()
    cat_conditions = []
    seen_cats = set()
    shops_lower = set()

    for p in sig_products:
        sn = (p.shop_name or "").strip()
        if sn:
            shops_lower.add(sn.lower())

        cat = (p.category or "").strip()
        sub = (p.subcategory or "").strip()
        if cat:
            cl = cat.lower()
            if cl not in seen_cats:
                seen_cats.add(cl)
                ce = category_field_equals_ci(Product.category, cat)
                if ce is not None:
                    cat_conditions.append(ce)
            if sub:
                pl = (cat.lower(), sub.lower())
                if pl not in seen_pairs:
                    seen_pairs.add(pl)
                    ce = category_field_equals_ci(Product.category, cat)
                    se = category_field_equals_ci(Product.subcategory, sub)
                    if ce is not None and se is not None:
                        pair_conditions.append(and_(ce, se))

    shop_conditions = []
    for sl in shops_lower:
        shop_conditions.append(sql_func.lower(sql_func.trim(Product.shop_name)) == sl)

    if not pair_conditions and not cat_conditions and not shop_conditions:
        return _fallback_popularity(db, skip, limit)

    whens = []
    if pair_conditions:
        whens.append((or_(*pair_conditions), 3))
    if cat_conditions:
        whens.append((or_(*cat_conditions), 2))
    if shop_conditions:
        whens.append((or_(*shop_conditions), 1))

    tier_col = case(*whens, else_=0)

    base = db.query(Product).filter(Product.is_active == True)  # noqa: E712
    total = base.count()
    products = (
        base.order_by(
            tier_col.desc(),
            Product.purchases.desc().nullslast(),
            Product.id,
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return products, total, True
