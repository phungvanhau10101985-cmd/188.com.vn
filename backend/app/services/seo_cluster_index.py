"""SEO cluster: index policy, cat3 → /c/<slug>, gắn cluster_slug lên menu/tile."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.utils.ttl_cache import cache as ttl_cache

# Trang /c/ trống không đưa Google index. Có hàng thì tôn trọng index_policy admin.
MIN_CLUSTER_INDEX_PRODUCTS = 1
_LOOKUP_KEY = "cat3_cluster_slug_lookup_v1"
_LOOKUP_TTL = 60.0


def cluster_is_indexable(index_policy: Optional[str], product_count: Optional[int]) -> bool:
    policy = (index_policy or "index").strip().lower()
    if policy == "noindex":
        return False
    return int(product_count or 0) >= MIN_CLUSTER_INDEX_PRODUCTS


def _fetch_cluster_slug_lookup() -> Dict[str, Dict[str, str]]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Category.slug, Category.name, SeoCluster.slug)
            .outerjoin(SeoCluster, Category.seo_cluster_id == SeoCluster.id)
            .filter(Category.level == 3)
            .all()
        )
        by_slug: Dict[str, str] = {}
        by_name: Dict[str, str] = {}
        for slug, name, cslug in rows:
            if not cslug:
                continue
            s = (slug or "").strip().lower()
            n = (name or "").strip().lower()
            if s:
                by_slug[s] = cslug
            if n:
                by_name[n] = cslug
        return {"by_slug": by_slug, "by_name": by_name}
    finally:
        db.close()


def cluster_slug_lookup() -> Dict[str, Dict[str, str]]:
    return ttl_cache.get_or_fetch(_LOOKUP_KEY, _LOOKUP_TTL, _fetch_cluster_slug_lookup)


def resolve_cluster_slug_for_cat3(
    *,
    slug: Optional[str] = None,
    name: Optional[str] = None,
    lookup: Optional[Dict[str, Dict[str, str]]] = None,
) -> Optional[str]:
    data = lookup or cluster_slug_lookup()
    s = (slug or "").strip().lower()
    n = (name or "").strip().lower()
    if s and s in data.get("by_slug", {}):
        return data["by_slug"][s]
    if n and n in data.get("by_name", {}):
        return data["by_name"][n]
    return None


def cat3_cluster_canonical_path(db: Session, category_path: str) -> Optional[str]:
    """Path `/danh-muc` 3 đoạn → `/c/<cluster>` nếu cat3 đã gắn cluster."""
    parts = [p for p in (category_path or "").strip().strip("/").lower().split("/") if p]
    if len(parts) < 3:
        return None
    leaf = parts[-1]
    full_slug = "/".join(parts[-3:])
    cat = (
        db.query(Category)
        .filter(Category.level == 3, Category.full_slug == full_slug)
        .first()
    )
    if not cat:
        cat = db.query(Category).filter(Category.level == 3, Category.slug == leaf).first()
    if not cat or not cat.seo_cluster_id:
        return None
    cluster = db.query(SeoCluster).filter(SeoCluster.id == cat.seo_cluster_id).first()
    if not cluster or not (cluster.slug or "").strip():
        return None
    return f"/c/{cluster.slug.strip()}"


def with_cluster_slugs_on_menu_tree(tree: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Gắn cluster_slug lên cat3 mà không mutate bản cache menu."""
    if not tree:
        return tree
    lookup = cluster_slug_lookup()
    out: List[Dict[str, Any]] = []
    for c1 in tree:
        children2_out: List[Dict[str, Any]] = []
        for c2 in c1.get("children") or []:
            children3_out: List[Any] = []
            for c3 in c2.get("children") or []:
                if isinstance(c3, dict):
                    existing = (c3.get("cluster_slug") or "").strip() or None
                    if existing:
                        children3_out.append(c3)
                    else:
                        slug = resolve_cluster_slug_for_cat3(
                            slug=c3.get("slug"),
                            name=c3.get("name"),
                            lookup=lookup,
                        )
                        children3_out.append({**c3, "cluster_slug": slug})
                else:
                    name = str(c3)
                    children3_out.append(
                        {
                            "name": name,
                            "slug": name,
                            "cluster_slug": resolve_cluster_slug_for_cat3(name=name, lookup=lookup),
                        }
                    )
            children2_out.append({**c2, "children": children3_out})
        out.append({**c1, "children": children2_out})
    return out


def with_cluster_slugs_on_tiles(tiles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not tiles:
        return tiles
    lookup = cluster_slug_lookup()
    out: List[Dict[str, Any]] = []
    for t in tiles:
        if int(t.get("level") or 0) != 3:
            out.append(t)
            continue
        if (t.get("cluster_slug") or "").strip():
            out.append(t)
            continue
        slug = resolve_cluster_slug_for_cat3(
            name=t.get("sub_subcategory") or t.get("name"),
            lookup=lookup,
        )
        out.append({**t, "cluster_slug": slug})
    return out


def cluster_parent_chain(
    db: Session, cat3: Category
) -> Tuple[Optional[Category], Optional[Category]]:
    parent = db.query(Category).filter(Category.id == cat3.parent_id).first() if cat3.parent_id else None
    grand = (
        db.query(Category).filter(Category.id == parent.parent_id).first()
        if parent and parent.parent_id
        else None
    )
    return parent, grand
