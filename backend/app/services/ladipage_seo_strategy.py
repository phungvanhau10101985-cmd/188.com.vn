"""Phân vai SEO: danh mục/cluster = head keyword; ladipage = long-tail / USP (chất liệu, bộ sưu tập)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.category_seo import CategorySeoMeta
from app.models.ladipage import Ladipage
from app.models.product import Product
from app.models.seo_cluster import SeoCluster
from app.services.ladipage_ai_service import normalize_material_filter
from app.services.ladipage_cleanup import _normalize_product_ids
from app.services.ladipage_public_url import is_single_product_ladipage

_BRAND_SUFFIX_RE = re.compile(r"\s*[|–—-]\s*188\.com\.vn\s*$", re.I)
_WS_RE = re.compile(r"\s+")


def normalize_seo_compare_text(raw: Optional[str]) -> str:
    t = (raw or "").strip().lower()
    t = _BRAND_SUFFIX_RE.sub("", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def suggest_category_ladipage_title(category_name: str, material_filter: Optional[str]) -> str:
    """Title mặc định có USP — tránh trùng H1/meta danh mục."""
    cat = (category_name or "").strip() or "Bộ sưu tập"
    material = normalize_material_filter(material_filter)
    if material:
        return f"{cat} - {material}"
    return f"{cat} - Bộ sưu tập mới"


def get_category_seo_competitor(db: Session, category_id: Optional[int]) -> Dict[str, Any]:
    """Thông tin trang SEO chính (danh mục / cluster) để so meta và link chéo."""
    empty: Dict[str, Any] = {
        "category_id": None,
        "category_name": None,
        "full_slug": None,
        "catalog_path": None,
        "seo_path": None,
        "seo_description": None,
        "head_title": None,
        "cluster_slug": None,
        "cluster_name": None,
    }
    if not category_id:
        return empty
    cat = db.query(Category).filter(Category.id == int(category_id)).first()
    if not cat:
        return empty

    full_slug = (cat.full_slug or "").strip().strip("/")
    catalog_path = f"/danh-muc/{full_slug}" if full_slug else None
    cluster_slug = None
    cluster_name = None
    seo_path = catalog_path
    if cat.seo_cluster_id:
        cluster = db.query(SeoCluster).filter(SeoCluster.id == cat.seo_cluster_id).first()
        if cluster and (cluster.slug or "").strip():
            cluster_slug = cluster.slug.strip()
            cluster_name = (cluster.name or "").strip() or None
            seo_path = f"/c/{cluster_slug}"

    seo_description = None
    if full_slug:
        meta = (
            db.query(CategorySeoMeta)
            .filter(CategorySeoMeta.category_path == full_slug.lower())
            .first()
        )
        if meta and (meta.seo_description or "").strip():
            seo_description = meta.seo_description.strip()

    head_title = cluster_name or (cat.name or "").strip() or None
    return {
        "category_id": cat.id,
        "category_name": (cat.name or "").strip() or None,
        "full_slug": full_slug or None,
        "catalog_path": catalog_path,
        "seo_path": seo_path,
        "seo_description": seo_description,
        "head_title": head_title,
        "cluster_slug": cluster_slug,
        "cluster_name": cluster_name,
    }


def seo_texts_collide(a: Optional[str], b: Optional[str], *, threshold: float = 0.92) -> bool:
    na = normalize_seo_compare_text(a)
    nb = normalize_seo_compare_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Subset: chỉ coi là trùng khi phần thêm quá ngắn (thiếu USP thật).
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 8 and shorter in longer:
        extra = longer.replace(shorter, " ", 1)
        extra = _WS_RE.sub(" ", extra).strip(" -–—|,")
        if len(extra) < 4:
            return True
        return False
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def ladipage_meta_missing_usp(meta_title: str, material_filter: Optional[str]) -> bool:
    material = normalize_material_filter(material_filter)
    if not material:
        return False
    title_n = normalize_seo_compare_text(meta_title)
    mat_n = normalize_seo_compare_text(material)
    return bool(mat_n) and mat_n not in title_n


def ensure_meta_has_material_usp(meta_title: str, material_filter: Optional[str], category_name: Optional[str]) -> str:
    """Ép USP chất liệu vào meta_title nếu AI quên."""
    title = (meta_title or "").strip()
    material = normalize_material_filter(material_filter)
    if not material or not title:
        return title
    if normalize_seo_compare_text(material) in normalize_seo_compare_text(title):
        return title
    brand = ""
    m = re.search(r"(\s*[|–—]\s*188\.com\.vn)\s*$", title, flags=re.I)
    if m:
        brand = m.group(1)
        title = title[: m.start()].rstrip()
    base = title or (category_name or "Bộ sưu tập")
    next_title = f"{base} {material}".strip()
    if brand:
        room = 60 - len(brand)
        if room > 12:
            next_title = next_title[:room].rstrip()
        next_title = f"{next_title}{brand}"
    elif len(next_title) > 60:
        next_title = next_title[:60].rsplit(" ", 1)[0].strip()
    return next_title


def differentiate_from_category_head(
    meta_title: str,
    *,
    head_title: Optional[str],
    material_filter: Optional[str],
    category_name: Optional[str],
) -> str:
    title = ensure_meta_has_material_usp(meta_title, material_filter, category_name)
    if not seo_texts_collide(title, head_title) and not seo_texts_collide(title, category_name):
        return title
    material = normalize_material_filter(material_filter)
    usp = material or "bộ sưu tập"
    base = (category_name or head_title or "Bộ sưu tập").strip()
    candidate = f"{base} - {usp}"
    if seo_texts_collide(candidate, head_title):
        candidate = f"Bộ sưu tập {usp} — {base}"
    if len(candidate) > 60:
        candidate = candidate[:60].rsplit(" ", 1)[0].strip()
    return candidate


def build_seo_collision_warning(
    meta_title: Optional[str],
    meta_description: Optional[str],
    competitor: Dict[str, Any],
    material_filter: Optional[str],
) -> Optional[str]:
    warnings: List[str] = []
    head = competitor.get("head_title") or competitor.get("category_name")
    if seo_texts_collide(meta_title, head) or seo_texts_collide(meta_title, competitor.get("category_name")):
        warnings.append("meta title gần trùng trang SEO danh mục/cluster — bổ sung USP (chất liệu/góc bộ sưu tập)")
    if ladipage_meta_missing_usp(meta_title or "", material_filter):
        warnings.append("meta title chưa chứa chất liệu đã lọc")
    cat_desc = competitor.get("seo_description")
    if cat_desc and seo_texts_collide(meta_description, cat_desc, threshold=0.9):
        warnings.append("meta description gần trùng mô tả SEO danh mục")
    if not warnings:
        return None
    return "; ".join(warnings)


def apply_ladipage_seo_guardrails(
    seo: Dict[str, str],
    *,
    competitor: Dict[str, Any],
    material_filter: Optional[str],
    category_name: Optional[str],
) -> Tuple[Dict[str, str], Optional[str]]:
    title = differentiate_from_category_head(
        seo.get("meta_title") or "",
        head_title=competitor.get("head_title"),
        material_filter=material_filter,
        category_name=category_name or competitor.get("category_name"),
    )
    desc = (seo.get("meta_description") or "").strip()
    material = normalize_material_filter(material_filter)
    if material and normalize_seo_compare_text(material) not in normalize_seo_compare_text(desc):
        prefix = f"Bộ sưu tập {material}. "
        desc = (prefix + desc).strip()
        if len(desc) > 160:
            desc = desc[:160].rsplit(" ", 1)[0].strip()
    out = {"meta_title": title, "meta_description": desc}
    warning = build_seo_collision_warning(title, desc, competitor, material_filter)
    return out, warning


def get_dominant_category_for_products(
    db: Session, product_ids: List[int], *, min_share: float = 0.6
) -> Optional[int]:
    """Danh mục chiếm đa số trong tập SP đã chọn — dùng canh SEO/link chéo cho ladipage nhiều SP.

    Trả None nếu SP quá tản mác (không danh mục nào áp đảo) — tránh gán sai USP.
    """
    ids = [int(x) for x in product_ids if x]
    if not ids:
        return None
    rows = (
        db.query(Product.category_id, func.count(Product.id))
        .filter(Product.id.in_(ids), Product.category_id.isnot(None))
        .group_by(Product.category_id)
        .all()
    )
    if not rows:
        return None
    total = sum(cnt for _, cnt in rows)
    if total <= 0:
        return None
    cat_id, cnt = max(rows, key=lambda r: r[1])
    if (cnt / total) >= min_share:
        return int(cat_id)
    return None


def resolve_ladipage_category_competitor(
    db: Session,
    lp: Ladipage,
    resolved_product_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Trang SEO chính liên quan tới ladipage: category_id thật (ladipage danh mục) hoặc
    danh mục chiếm đa số trong SP đã chọn (ladipage nhiều SP). Dùng chung cho guardrail + link chéo.
    """
    if lp.source_type == "category" and lp.category_id:
        return get_category_seo_competitor(db, lp.category_id)
    if lp.source_type == "products":
        ids = resolved_product_ids if resolved_product_ids is not None else _normalize_product_ids(lp.product_ids)
        if len(ids) > 1:
            dominant_id = get_dominant_category_for_products(db, ids)
            if dominant_id:
                return get_category_seo_competitor(db, dominant_id)
    return get_category_seo_competitor(db, None)


def suggest_multi_product_ladipage_title(base_title: str, category_name: Optional[str]) -> str:
    """Title cho ladipage nhiều SP khi trùng gần tên danh mục chiếm đa số — thêm USP bộ sưu tập."""
    base = (base_title or "").strip() or "Bộ sưu tập nổi bật"
    cat = (category_name or "").strip()
    if not cat:
        return base
    return f"{cat} - Bộ sưu tập chọn lọc"


def list_published_category_ladipages(
    db: Session,
    *,
    category_ids: List[int],
    limit: int = 12,
    exclude_ladipage_id: Optional[int] = None,
) -> List[Ladipage]:
    ids = [int(x) for x in category_ids if x]
    if not ids:
        return []
    q = (
        db.query(Ladipage)
        .filter(
            Ladipage.status == "published",
            Ladipage.source_type == "category",
            Ladipage.category_id.in_(ids),
        )
        .order_by(Ladipage.published_at.desc(), Ladipage.id.desc())
    )
    if exclude_ladipage_id:
        q = q.filter(Ladipage.id != int(exclude_ladipage_id))
    rows = q.limit(max(1, min(limit, 48))).all()
    return [lp for lp in rows if not is_single_product_ladipage(lp)]


def list_related_ladipages_for_categories(
    db: Session,
    *,
    category_ids: List[int],
    limit: int = 8,
    exclude_ladipage_id: Optional[int] = None,
    multi_product_scan_limit: int = 60,
) -> List[Ladipage]:
    """Ladipage đã publish liên quan tới (các) danh mục — gồm ladipage danh mục trực tiếp
    và ladipage nhiều SP có danh mục chiếm đa số khớp (cross-link 2 chiều đầy đủ).
    """
    ids_set = {int(x) for x in category_ids if x}
    if not ids_set:
        return []

    direct = list_published_category_ladipages(
        db,
        category_ids=list(ids_set),
        limit=limit,
        exclude_ladipage_id=exclude_ladipage_id,
    )
    if len(direct) >= limit:
        return direct[:limit]

    remaining = limit - len(direct)
    multi_candidates = (
        db.query(Ladipage)
        .filter(Ladipage.status == "published", Ladipage.source_type == "products")
        .order_by(Ladipage.published_at.desc(), Ladipage.id.desc())
        .limit(max(1, min(multi_product_scan_limit, 200)))
        .all()
    )
    matched: List[Ladipage] = []
    for lp in multi_candidates:
        if exclude_ladipage_id and lp.id == exclude_ladipage_id:
            continue
        ids = _normalize_product_ids(lp.product_ids)
        if len(ids) <= 1:
            continue
        dominant_id = get_dominant_category_for_products(db, ids)
        if dominant_id and dominant_id in ids_set:
            matched.append(lp)
        if len(matched) >= remaining:
            break
    return direct + matched
