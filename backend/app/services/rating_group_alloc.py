"""
Cấp mã nhóm đánh giá mới cho danh mục cấp 3 tạo lúc cào/import.

Mã không trùng nhóm đánh giá có sẵn (bảng từ-khóa), mã dự phòng 0/888/1000,
nhóm câu hỏi 88/99/100, và mọi mã đã gắn trên danh mục / sản phẩm / đánh giá.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models.category import Category
from app.services.product_rating_question_groups import (
    RATING_GROUP_ID_UNASSIGNED,
    RATING_GROUP_ID_WHITELIST,
)

# 0/1000 bị coalesce coi là trống; 888 = chưa gán; 88/99/100 là nhóm câu hỏi (88 cũng là nhóm bóng golf).
_HARD_RESERVED: Set[int] = set(RATING_GROUP_ID_WHITELIST) | {
    0,
    88,
    99,
    100,
    1000,
    RATING_GROUP_ID_UNASSIGNED,
}
_ALLOC_START = 101
_ALLOC_LIMIT = 1_000_000


def _table_names(db: Session) -> Set[str]:
    """Dùng connection của session — SQLite :memory: không chia sẻ bảng giữa các connection."""
    try:
        return set(sa_inspect(db.connection()).get_table_names())
    except Exception:
        return set()


def _distinct_positive(rows) -> Set[int]:
    out: Set[int] = set()
    for row in rows:
        raw = row
        if not isinstance(row, (int, float, str)):
            try:
                raw = row[0]
            except Exception:
                raw = row
        try:
            val = int(raw)
        except (TypeError, ValueError):
            continue
        if val > 0:
            out.add(val)
    return out


def used_rating_group_ids(db: Session) -> Set[int]:
    """Mọi mã không được cấp lại."""
    used = set(_HARD_RESERVED)
    used |= _distinct_positive(
        db.query(Category.rating_group_id).filter(Category.rating_group_id.isnot(None)).all()
    )
    names = _table_names(db)
    if "products" in names:
        from app.models.product import Product

        used |= _distinct_positive(
            db.query(Product.group_rating).filter(Product.group_rating.isnot(None)).distinct().all()
        )
    if "product_reviews" in names:
        from app.models.product_review import ProductReview

        used |= _distinct_positive(
            db.query(ProductReview.group).filter(ProductReview.group.isnot(None)).distinct().all()
        )
    return used


def allocate_rating_group_id(db: Session, extra_used: Optional[Iterable[int]] = None) -> int:
    """Mã nguyên dương mới, không trùng nhóm đã có.

    Truyền cùng một ``set`` cho nhiều danh mục tạo trong một lượt để không query lại
    giữa các lần flush (query giữa chừng làm lệch identity map của session).
    """
    if isinstance(extra_used, set):
        used = extra_used
    else:
        used = used_rating_group_ids(db)
        if extra_used:
            used.update(int(x) for x in extra_used)
    n = _ALLOC_START
    while n in used:
        n += 1
        if n > _ALLOC_LIMIT:
            raise RuntimeError("hết dải mã nhóm đánh giá")
    used.add(n)
    return n


def _category_path(cat: Category, by_id: Dict[int, Category]) -> str:
    parts: List[str] = []
    cur: Optional[Category] = cat
    seen: Set[int] = set()
    while cur is not None and cur.id not in seen:
        seen.add(int(cur.id))
        name = (cur.name or "").strip()
        if name:
            parts.append(name)
        parent_id = cur.parent_id
        cur = by_id.get(int(parent_id)) if parent_id else None
    parts.reverse()
    return " / ".join(parts)


def list_rating_groups_without_reviews(db: Session) -> List[Dict[str, Any]]:
    """
    Nhóm đánh giá của danh mục cấp 3 mới, chưa có bản ghi đánh giá nào mang mã đó.
    """
    cats = (
        db.query(Category)
        .filter(
            Category.level == 3,
            Category.rating_group_id.isnot(None),
            Category.is_active.is_(True),
        )
        .order_by(Category.id.asc())
        .all()
    )
    if not cats:
        return []
    by_id = {int(r.id): r for r in db.query(Category).all()}
    group_ids = [int(c.rating_group_id) for c in cats if c.rating_group_id]
    reviewed: Set[int] = set()
    if "product_reviews" in _table_names(db) and group_ids:
        from app.models.product_review import ProductReview

        reviewed = _distinct_positive(
            db.query(ProductReview.group).filter(ProductReview.group.in_(group_ids)).distinct().all()
        )
    items: List[Dict[str, Any]] = []
    for cat in cats:
        gid = int(cat.rating_group_id or 0)
        if gid <= 0 or gid in reviewed:
            continue
        items.append(
            {
                "rating_group_id": gid,
                "level": int(cat.level or 0),
                "category_id": int(cat.id),
                "category_name": (cat.name or "").strip(),
                "category_path": _category_path(cat, by_id),
                "full_slug": (cat.full_slug or "").strip(),
            }
        )
    return items
