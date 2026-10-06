"""
Import Excel: sản phẩm nhận nhóm đánh giá của danh mục cấp 3.

- Cat3 đã có mã riêng → gán mã đó lên sản phẩm.
- Cat3 chưa có mã, file mang mã riêng (không phải nhóm dùng chung) → gắn mã vào cat3.
- Chưa có cat3 và file mang mã riêng → tạo nhánh danh mục, giữ mã đó nếu còn trống.
- Nhóm chưa có đánh giá → sinh 100 đánh giá dựng sẵn theo tên danh mục cấp 3.
Nhóm dùng chung (14, 24, … và 888) giữ nguyên trên sản phẩm, không ghi lên danh mục.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.category import Category
from app.services.taxonomy_auto_create import (
    _dedicated_rating_group_id,
    _find_child_by_name,
    _find_level1,
    _name_key,
    _seed_group_reviews,
    ensure_additive_category_triple,
)

_CacheValue = Tuple[int, int]


def _labels(product_data: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        str(product_data.get("category") or "").strip(),
        str(product_data.get("subcategory") or "").strip(),
        str(product_data.get("sub_subcategory") or "").strip(),
    )


def _file_group(product_data: Dict[str, Any]) -> int:
    raw = product_data.get("group_rating")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _load_cat3(db: Session, category_id: Any) -> Optional[Category]:
    try:
        cid = int(category_id or 0)
    except (TypeError, ValueError):
        return None
    if cid <= 0:
        return None
    cat = db.query(Category).filter(Category.id == cid, Category.level == 3).first()
    return cat


def _find_cat3(db: Session, cat1: str, cat2: str, cat3: str) -> Optional[Category]:
    if not (cat1 and cat2 and cat3):
        return None
    c1 = _find_level1(db, cat1)
    if c1 is None:
        return None
    c2 = _find_child_by_name(db, int(c1.id), 2, cat2)
    if c2 is None:
        return None
    return _find_child_by_name(db, int(c2.id), 3, cat3)


def _path_names(db: Session, cat3: Category, cat1: str, cat2: str) -> Tuple[str, str, str]:
    c2 = db.query(Category).filter(Category.id == cat3.parent_id).first() if cat3.parent_id else None
    c1 = db.query(Category).filter(Category.id == c2.parent_id).first() if c2 and c2.parent_id else None
    return (
        (c1.name if c1 and c1.name else cat1) or cat1,
        (c2.name if c2 and c2.name else cat2) or cat2,
        (cat3.name or "").strip(),
    )


def _index_cat3(cat3_idx: Optional[Dict[str, Dict[str, int]]], cat: Optional[Category]) -> None:
    if not cat3_idx or cat is None or int(cat.level or 0) != 3:
        return
    cid = int(cat.id)
    if cat.full_slug:
        cat3_idx["by_full_slug"][cat.full_slug.strip().lower()] = cid
    if cat.slug:
        cat3_idx["by_slug"].setdefault(cat.slug.strip().lower(), cid)
    if cat.name:
        cat3_idx["by_name"].setdefault(cat.name.strip().lower(), cid)


def _remember(cache: Optional[Dict[Any, _CacheValue]], keys: List[Any], gid: int, cid: int) -> None:
    if cache is None:
        return
    payload: _CacheValue = (int(gid or 0), int(cid or 0))
    for key in keys:
        cache[key] = payload


def _apply_cached(product_data: Dict[str, Any], gid: int, cid: int) -> None:
    if gid > 0:
        product_data["group_rating"] = gid
    if cid > 0:
        product_data["category_id"] = cid


def apply_import_category_rating_group(
    db: Session,
    product_data: Dict[str, Any],
    *,
    cat3_idx: Optional[Dict[str, Dict[str, int]]] = None,
    cache: Optional[Dict[Any, _CacheValue]] = None,
    read_cache: Optional[Dict[Any, _CacheValue]] = None,
) -> List[str]:
    """Gán nhóm đánh giá của cat3 vào sản phẩm và sinh đánh giá nếu nhóm còn trống.

    ``cache`` ghi kết quả của dòng này. ``read_cache`` là các dòng đã ghi thành công
    trong cùng lượt import — tách riêng để dòng bị rollback không giữ cache.
    """
    if not isinstance(product_data, dict):
        return []

    cat1, cat2, cat3_name = _labels(product_data)
    file_gid = _file_group(product_data)
    dedicated = _dedicated_rating_group_id(file_gid)
    category_id = product_data.get("category_id")

    keys: List[Any] = []
    if cat1 and cat2 and cat3_name:
        keys.append(("name", _name_key(cat1), _name_key(cat2), _name_key(cat3_name)))
    try:
        cid_key = int(category_id or 0)
    except (TypeError, ValueError):
        cid_key = 0
    if cid_key > 0:
        keys.append(("id", cid_key))

    lookup = read_cache if read_cache is not None else cache
    if lookup is not None:
        for key in keys:
            hit = lookup.get(key)
            if hit is not None:
                _apply_cached(product_data, hit[0], hit[1])
                return []

    warnings: List[str] = []
    cat3 = _load_cat3(db, category_id) or _find_cat3(db, cat1, cat2, cat3_name)

    if cat3 is not None and cat3.rating_group_id:
        gid = int(cat3.rating_group_id)
        n1, n2, n3 = _path_names(db, cat3, cat1, cat2)
        product_data["group_rating"] = gid
        product_data["category_id"] = int(cat3.id)
        _index_cat3(cat3_idx, cat3)
        _seed_group_reviews(
            db, gid, cat1=n1, cat2=n2, cat3=n3, warnings=warnings, label="import"
        )
        if file_gid != gid:
            warnings.append(f"import: sản phẩm nhận nhóm đánh giá {gid} của danh mục «{n3}».")
        _remember(
            cache,
            keys + [("id", int(cat3.id)), ("name", _name_key(n1), _name_key(n2), _name_key(n3))],
            gid,
            int(cat3.id),
        )
        return warnings

    if cat3 is not None and dedicated:
        owner = db.query(Category).filter(Category.rating_group_id == dedicated).first()
        n1, n2, n3 = _path_names(db, cat3, cat1, cat2)
        product_data["category_id"] = int(cat3.id)
        product_data["group_rating"] = dedicated
        _index_cat3(cat3_idx, cat3)
        if owner is None:
            cat3.rating_group_id = dedicated
            db.flush()
            warnings.append(f"import: danh mục «{n3}» nhận nhóm đánh giá {dedicated}.")
            _seed_group_reviews(
                db,
                dedicated,
                cat1=n1,
                cat2=n2,
                cat3=n3,
                warnings=warnings,
                label="import",
            )
        else:
            on1, on2, on3 = _path_names(db, owner, n1, n2)
            _seed_group_reviews(
                db,
                dedicated,
                cat1=on1,
                cat2=on2,
                cat3=on3,
                warnings=warnings,
                label="import",
            )
        _remember(cache, keys + [("id", int(cat3.id))], dedicated, int(cat3.id))
        return warnings

    if cat3 is not None:
        product_data["category_id"] = int(cat3.id)
        _index_cat3(cat3_idx, cat3)
        _remember(cache, keys + [("id", int(cat3.id))], 0, int(cat3.id))
        return []

    if not dedicated or not (cat1 and cat2 and cat3_name):
        return []

    created, create_warnings = ensure_additive_category_triple(
        db,
        cat1,
        cat2,
        cat3_name,
        preferred_rating_group_id=dedicated,
    )
    warnings.extend(create_warnings)
    if not created:
        return warnings

    try:
        cid = int(created.get("category_id") or 0)
    except (TypeError, ValueError):
        cid = 0
    try:
        gid = int(created.get("rating_group_id") or 0)
    except (TypeError, ValueError):
        gid = 0
    if gid > 0:
        product_data["group_rating"] = gid
    if cid > 0:
        product_data["category_id"] = cid
        cat = db.query(Category).filter(Category.id == cid).first()
        _index_cat3(cat3_idx, cat)
        keys.append(("id", cid))
    _remember(cache, keys, gid, cid)
    return warnings
