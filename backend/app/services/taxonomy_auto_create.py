"""
Bổ sung taxonomy khi import/cào thiếu nhánh: chỉ **thêm** cat thiếu, không sửa nhánh cũ.

Cascade:
- Có cat1 + cat2 → chỉ tạo cat3
- Có cat1 → tạo cat2 + cat3
- Không có cat1 → tạo cả cat1 + cat2 + cat3

Nhánh mới có ``external_id`` prefix ``auto__`` để phân biệt với taxonomy_import;
lần sau ``load_active_category_triples`` thấy như taxonomy chuẩn.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.utils.slug import create_slug

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
_AUTO_EXT_PREFIX = "auto__"
_MAX_NAME_LEN = 120


def _norm_label(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _name_key(text: str) -> str:
    return _norm_label(text).casefold()


def _slug_key(text: str) -> str:
    return create_slug(_norm_label(text))


def validate_proposed_category_names(cat1: str, cat2: str, cat3: str) -> Optional[str]:
    """Trả message lỗi hoặc None nếu hợp lệ để tạo/gán."""
    n1, n2, n3 = _norm_label(cat1), _norm_label(cat2), _norm_label(cat3)
    if not (n1 and n2 and n3):
        return "thiếu cat1/cat2/cat3"
    if len(n1) > _MAX_NAME_LEN or len(n2) > _MAX_NAME_LEN or len(n3) > _MAX_NAME_LEN:
        return "tên danh mục quá dài"
    if _CJK_RE.search(n1 + n2 + n3):
        return "cat1–cat3 chứa ký tự CJK"
    if not (_slug_key(n1) and _slug_key(n2) and _slug_key(n3)):
        return "slug danh mục rỗng sau chuẩn hoá"
    return None


def _find_level1(db: Session, name: str) -> Optional[Category]:
    want = _name_key(name)
    want_slug = _slug_key(name)
    rows = (
        db.query(Category)
        .filter(Category.level == 1, Category.is_active.is_(True))
        .all()
    )
    for r in rows:
        if _name_key(r.name or "") == want:
            return r
    for r in rows:
        if (r.slug or "").strip() == want_slug or _slug_key(r.name or "") == want_slug:
            return r
    return None


def _find_child_by_name(db: Session, parent_id: int, level: int, name: str) -> Optional[Category]:
    want = _name_key(name)
    want_slug = _slug_key(name)
    rows = (
        db.query(Category)
        .filter(
            Category.parent_id == parent_id,
            Category.level == level,
            Category.is_active.is_(True),
        )
        .all()
    )
    for r in rows:
        if _name_key(r.name or "") == want:
            return r
    for r in rows:
        if (r.slug or "").strip() == want_slug or _slug_key(r.name or "") == want_slug:
            return r
    return None


def _full_slug_taken(db: Session, full_slug: str, *, exclude_id: Optional[int] = None) -> bool:
    q = db.query(Category.id).filter(Category.full_slug == full_slug)
    if exclude_id is not None:
        q = q.filter(Category.id != exclude_id)
    return q.first() is not None


def _unique_full_slug(db: Session, base: str) -> str:
    candidate = (base or "").strip().strip("/")
    if not candidate:
        candidate = "danh-muc"
    if not _full_slug_taken(db, candidate):
        return candidate
    i = 2
    while i < 50:
        alt = f"{candidate}-{i}"
        if not _full_slug_taken(db, alt):
            return alt
        i += 1
    return f"{candidate}-{create_slug(str(id(candidate)))[:8]}"


def _ext_id_taken(db: Session, ext_id: str) -> bool:
    return db.query(Category.id).filter(Category.external_id == ext_id).first() is not None


def _unique_external_id(db: Session, base: str) -> str:
    candidate = (base or "").strip()[:180]
    if not candidate:
        candidate = f"{_AUTO_EXT_PREFIX}cat"
    if not _ext_id_taken(db, candidate):
        return candidate
    i = 2
    while i < 50:
        alt = f"{candidate}__{i}"[:200]
        if not _ext_id_taken(db, alt):
            return alt
        i += 1
    return f"{candidate}__x"[:200]


def _unique_cluster_external_id(db: Session, base: str) -> str:
    candidate = (base or "").strip()[:200]
    if not candidate:
        candidate = f"{_AUTO_EXT_PREFIX}cluster"
    if not db.query(SeoCluster.id).filter(SeoCluster.external_id == candidate).first():
        return candidate
    i = 2
    while i < 50:
        alt = f"{candidate}__{i}"[:200]
        if not db.query(SeoCluster.id).filter(SeoCluster.external_id == alt).first():
            return alt
        i += 1
    return f"{candidate}__x"[:200]


def _ensure_seo_cluster_for_cat3(db: Session, cat3: Category) -> None:
    """Tạo cluster 1:1 nếu cat3 mới chưa có — không đụng cluster cũ."""
    if cat3.seo_cluster_id:
        return
    slug = (cat3.slug or "").strip() or _slug_key(cat3.name or "danh-muc")
    ext = _unique_cluster_external_id(db, f"{_AUTO_EXT_PREFIX}cluster__{slug}")

    cluster_slug = slug
    n = 2
    while db.query(SeoCluster.id).filter(SeoCluster.slug == cluster_slug).first():
        cluster_slug = f"{slug}-{n}"
        n += 1
        if n > 50:
            break

    cluster = SeoCluster(
        external_id=ext,
        slug=cluster_slug,
        name=(cat3.name or cluster_slug)[:500],
        canonical_path=f"/c/{cluster_slug}",
        index_policy="index",
        source="auto_taxonomy_create",
        notes="Tạo tự động khi bổ sung cat3 từ import/cào.",
    )
    db.add(cluster)
    db.flush()
    cat3.seo_cluster_id = cluster.id


def _create_category(
    db: Session,
    *,
    level: int,
    name: str,
    parent: Optional[Category],
    leaf_slug: str,
    full_slug: str,
) -> Category:
    name_n = _norm_label(name)[:255]
    parent_slug_parts: List[str] = []
    if parent and parent.full_slug:
        parent_slug_parts = [p for p in parent.full_slug.split("/") if p]
    if level == 1:
        ext_base = f"{_AUTO_EXT_PREFIX}cat1__{leaf_slug}"
    elif level == 2:
        c1s = parent_slug_parts[0] if parent_slug_parts else "cat1"
        ext_base = f"{_AUTO_EXT_PREFIX}cat2__{c1s}__{leaf_slug}"
    else:
        c1s = parent_slug_parts[0] if parent_slug_parts else "cat1"
        c2s = parent_slug_parts[1] if len(parent_slug_parts) > 1 else "cat2"
        ext_base = f"{_AUTO_EXT_PREFIX}cat3__{c1s}__{c2s}__{leaf_slug}"

    cat = Category(
        external_id=_unique_external_id(db, ext_base),
        parent_id=parent.id if parent else None,
        level=level,
        name=name_n,
        slug=leaf_slug[:300],
        full_slug=_unique_full_slug(db, full_slug)[:800],
        sort_order=0,
        is_active=True,
        # cat1/cat2 index; cat3 noindex (gom cluster)
        seo_index=(level in (1, 2)),
    )
    db.add(cat)
    db.flush()
    return cat


def ensure_additive_category_triple(
    db: Session,
    cat1: str,
    cat2: str,
    cat3: str,
) -> Tuple[Optional[Dict[str, str]], List[str]]:
    """
    Tìm hoặc tạo nhánh cat1/cat2/cat3 (additive only).

    Trả ``({cat1, cat2, cat3, full_slug, created_levels}, warnings)``.
    ``created_levels`` là chuỗi ``"1,2"`` / ``"3"`` / ``""`` (đã có đủ).
    """
    warnings: List[str] = []
    err = validate_proposed_category_names(cat1, cat2, cat3)
    if err:
        warnings.append(f"taxonomy_auto_create: bỏ qua tạo — {err}.")
        return None, warnings

    n1, n2, n3 = _norm_label(cat1), _norm_label(cat2), _norm_label(cat3)
    created: List[int] = []

    c1 = _find_level1(db, n1)
    if c1 is None:
        s1 = _slug_key(n1)
        c1 = _create_category(db, level=1, name=n1, parent=None, leaf_slug=s1, full_slug=s1)
        created.append(1)
        warnings.append(f"taxonomy_auto_create: đã tạo cat1 «{c1.name}».")
    else:
        # Dùng tên chuẩn trong DB — không rename
        n1 = (c1.name or n1).strip()

    c2 = _find_child_by_name(db, int(c1.id), 2, n2)
    if c2 is None:
        s2 = _slug_key(n2)
        fs2 = f"{(c1.slug or _slug_key(n1)).strip()}/{s2}"
        c2 = _create_category(db, level=2, name=n2, parent=c1, leaf_slug=s2, full_slug=fs2)
        created.append(2)
        warnings.append(f"taxonomy_auto_create: đã tạo cat2 «{c2.name}» dưới «{c1.name}».")
    else:
        n2 = (c2.name or n2).strip()

    c3 = _find_child_by_name(db, int(c2.id), 3, n3)
    if c3 is None:
        s3 = _slug_key(n3)
        fs3 = f"{(c1.slug or '').strip()}/{(c2.slug or '').strip()}/{s3}"
        c3 = _create_category(db, level=3, name=n3, parent=c2, leaf_slug=s3, full_slug=fs3)
        created.append(3)
        try:
            _ensure_seo_cluster_for_cat3(db, c3)
        except Exception as exc:
            logger.warning("taxonomy_auto_create: tạo seo_cluster thất bại: %s", exc)
            warnings.append(f"taxonomy_auto_create: cat3 đã tạo nhưng cluster lỗi — {exc}")
        warnings.append(f"taxonomy_auto_create: đã tạo cat3 «{c3.name}» dưới «{c1.name} / {c2.name}».")
    else:
        n3 = (c3.name or n3).strip()

    try:
        db.flush()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        warnings.append(f"taxonomy_auto_create: lỗi DB khi lưu nhánh — {exc}")
        return None, warnings

    if created:
        try:
            from app.crud import category_menu_cache as menu_cache_crud

            menu_cache_crud.invalidate_all_menu_caches()
        except Exception as exc:
            logger.warning("taxonomy_auto_create: invalidate menu cache: %s", exc)

    out: Dict[str, Any] = {
        "cat1": (c1.name or n1).strip(),
        "cat2": (c2.name or n2).strip(),
        "cat3": (c3.name or n3).strip(),
        "full_slug": (c3.full_slug or "").strip(),
        "created_levels": ",".join(str(x) for x in created),
        "category_id": str(c3.id),
    }
    if not created:
        warnings.append(
            f"taxonomy_auto_create: dùng nhánh có sẵn «{out['cat1']} / {out['cat2']} / {out['cat3']}»."
        )
    return out, warnings
