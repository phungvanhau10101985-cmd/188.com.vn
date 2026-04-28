"""CRUD for anonymous session behavior; merged into user tables on login."""
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.guest_behavior import GuestProductView, GuestFavorite, GuestSearchHistory
from app.schemas.user import ProductViewCreate, FavoriteCreate, SearchHistoryCreate
from app.crud import user as user_crud


def _norm_session(session_id: Optional[str]) -> Optional[str]:
    if not session_id or not str(session_id).strip():
        return None
    s = str(session_id).strip()
    if len(s) > 128:
        return s[:128]
    return s


def add_guest_product_view(db: Session, session_id: str, view_data: ProductViewCreate) -> GuestProductView:
    sid = _norm_session(session_id)
    if not sid:
        raise ValueError("session_id required")
    existing = (
        db.query(GuestProductView)
        .filter(GuestProductView.session_id == sid, GuestProductView.product_id == view_data.product_id)
        .first()
    )
    if existing:
        existing.view_count = (existing.view_count or 0) + 1
        existing.time_spent_seconds = view_data.time_spent_seconds or 0
        if view_data.product_data:
            existing.product_data = view_data.product_data
        existing.viewed_at = datetime.now()
        db.commit()
        db.refresh(existing)
        return existing
    row = GuestProductView(
        session_id=sid,
        product_id=view_data.product_id,
        product_data=view_data.product_data,
        time_spent_seconds=view_data.time_spent_seconds or 0,
        viewed_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_guest_viewed_products(db: Session, session_id: str, limit: int = 20) -> List[GuestProductView]:
    sid = _norm_session(session_id)
    if not sid:
        return []
    return (
        db.query(GuestProductView)
        .filter(GuestProductView.session_id == sid)
        .order_by(GuestProductView.viewed_at.desc())
        .limit(limit)
        .all()
    )


def recent_guest_view_product_ids(db: Session, session_id: str, limit: int = 8) -> List[int]:
    sid = _norm_session(session_id)
    if not sid:
        return []
    rows = (
        db.query(GuestProductView.product_id)
        .filter(GuestProductView.session_id == sid)
        .order_by(GuestProductView.viewed_at.desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


def add_guest_favorite(db: Session, session_id: str, favorite_data: FavoriteCreate) -> GuestFavorite:
    """Guest yêu thích: không tăng product.likes (tránh đếm đôi khi merge tài khoản)."""
    sid = _norm_session(session_id)
    if not sid:
        raise ValueError("session_id required")
    existing = (
        db.query(GuestFavorite)
        .filter(GuestFavorite.session_id == sid, GuestFavorite.product_id == favorite_data.product_id)
        .first()
    )
    if existing:
        if favorite_data.product_data:
            existing.product_data = favorite_data.product_data
        db.commit()
        db.refresh(existing)
        return existing
    row = GuestFavorite(
        session_id=sid,
        product_id=favorite_data.product_id,
        product_data=favorite_data.product_data,
        created_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_guest_favorite(db: Session, session_id: str, product_id: int) -> bool:
    sid = _norm_session(session_id)
    if not sid:
        return False
    fav = (
        db.query(GuestFavorite)
        .filter(GuestFavorite.session_id == sid, GuestFavorite.product_id == product_id)
        .first()
    )
    if not fav:
        return False
    db.delete(fav)
    db.commit()
    return True


def get_guest_favorites(db: Session, session_id: str, limit: int = 50) -> List[GuestFavorite]:
    sid = _norm_session(session_id)
    if not sid:
        return []
    return (
        db.query(GuestFavorite)
        .filter(GuestFavorite.session_id == sid)
        .order_by(GuestFavorite.created_at.desc())
        .limit(limit)
        .all()
    )


def is_guest_product_favorited(db: Session, session_id: str, product_id: int) -> bool:
    sid = _norm_session(session_id)
    if not sid:
        return False
    return (
        db.query(GuestFavorite)
        .filter(GuestFavorite.session_id == sid, GuestFavorite.product_id == product_id)
        .first()
        is not None
    )


def add_guest_search_history(db: Session, session_id: str, data: SearchHistoryCreate) -> GuestSearchHistory:
    sid = _norm_session(session_id)
    if not sid:
        raise ValueError("session_id required")
    row = GuestSearchHistory(
        session_id=sid,
        search_query=data.search_query,
        search_filters=data.search_filters,
        search_results_count=data.search_results_count or 0,
        searched_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_guest_search_history(db: Session, session_id: str, limit: int = 20) -> List[GuestSearchHistory]:
    sid = _norm_session(session_id)
    if not sid:
        return []
    return (
        db.query(GuestSearchHistory)
        .filter(GuestSearchHistory.session_id == sid)
        .order_by(GuestSearchHistory.searched_at.desc())
        .limit(limit)
        .all()
    )


def clear_guest_search_history(db: Session, session_id: str) -> None:
    sid = _norm_session(session_id)
    if not sid:
        return
    db.query(GuestSearchHistory).filter(GuestSearchHistory.session_id == sid).delete()
    db.commit()


def merge_guest_session_to_user(db: Session, user_id: int, session_id: str) -> dict:
    """Gộp hành vi phiên khách vào tài khoản; xóa bản ghi guest."""
    sid = _norm_session(session_id)
    if not sid:
        return {"merged_views": 0, "merged_favorites": 0, "merged_searches": 0}

    views = db.query(GuestProductView).filter(GuestProductView.session_id == sid).all()
    merged_views = 0
    for v in views:
        user_crud.add_product_view_with_data(
            db,
            user_id,
            ProductViewCreate(
                product_id=v.product_id,
                product_data=v.product_data,
                time_spent_seconds=v.time_spent_seconds or 0,
            ),
        )
        merged_views += 1
    db.query(GuestProductView).filter(GuestProductView.session_id == sid).delete()

    favs = db.query(GuestFavorite).filter(GuestFavorite.session_id == sid).all()
    merged_favs = 0
    for f in favs:
        user_crud.add_favorite_product_with_data(
            db,
            user_id,
            FavoriteCreate(product_id=f.product_id, product_data=f.product_data),
        )
        merged_favs += 1
    db.query(GuestFavorite).filter(GuestFavorite.session_id == sid).delete()

    searches = db.query(GuestSearchHistory).filter(GuestSearchHistory.session_id == sid).order_by(
        GuestSearchHistory.searched_at.asc()
    ).all()
    merged_srch = 0
    for s in searches:
        user_crud.add_search_history(
            db,
            user_id,
            SearchHistoryCreate(
                search_query=s.search_query,
                search_filters=s.search_filters,
                search_results_count=s.search_results_count or 0,
            ),
        )
        merged_srch += 1
    db.query(GuestSearchHistory).filter(GuestSearchHistory.session_id == sid).delete()

    db.commit()
    return {"merged_views": merged_views, "merged_favorites": merged_favs, "merged_searches": merged_srch}
