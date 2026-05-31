"""Dịch vụ cache bộ lọc listing — đọc/ghi DB, rebuild, invalidation."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.crud import listing_facet_cache as facet_cache_crud
from app.crud.listing_facet_cache import (
    SCOPE_CATEGORY_L1,
    SCOPE_CATEGORY_L2,
    SCOPE_CATEGORY_L3,
    SCOPE_SEARCH_Q,
    SCOPE_SEO_CLUSTER,
)
from app.models.category import Category
from app.models.listing_facet_cache import ListingFacetCache
from app.models.product import Product
from app.models.seo_cluster import SeoCluster

logger = logging.getLogger(__name__)

MIN_AUTO_CACHE_PRODUCT_COUNT = 200


def snapshot_product_for_facet_refresh(product: Any) -> SimpleNamespace:
    """Ảnh chụp các trường ảnh hưởng rebuild cache danh mục + từ khóa tìm kiếm."""
    return SimpleNamespace(
        category=getattr(product, "category", None),
        subcategory=getattr(product, "subcategory", None),
        sub_subcategory=getattr(product, "sub_subcategory", None),
        category_id=getattr(product, "category_id", None),
        name=getattr(product, "name", None),
        code=getattr(product, "code", None),
        material=getattr(product, "material", None),
        style=getattr(product, "style", None),
        color=getattr(product, "color", None),
        occasion=getattr(product, "occasion", None),
        features=getattr(product, "features", None),
        sizes=getattr(product, "sizes", None),
        product_info=getattr(product, "product_info", None),
    )


def _product_search_blob(product: Any) -> str:
    def _part(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    parts = (
        _part(getattr(product, "name", None)),
        _part(getattr(product, "code", None)),
        _part(getattr(product, "category", None)),
        _part(getattr(product, "subcategory", None)),
        _part(getattr(product, "sub_subcategory", None)),
        _part(getattr(product, "material", None)),
        _part(getattr(product, "style", None)),
        _part(getattr(product, "color", None)),
        _part(getattr(product, "occasion", None)),
        _part(getattr(product, "features", None)),
        _part(getattr(product, "sizes", None)),
        _part(getattr(product, "product_info", None)),
    )
    return " ".join(parts).lower()


def product_matches_search_keyword(product: Any, keyword: str) -> bool:
    """Khớp logic apply_product_search_word_filters (tất cả từ ilike trên chuỗi tổng hợp)."""
    from app.crud.product import normalize_search_query

    normalized = normalize_search_query(keyword or "")
    words = [w.strip() for w in normalized.split() if w.strip()]
    if not words:
        return False
    blob = _product_search_blob(product)
    return all(w.lower() in blob for w in words)


def iter_related_search_cache_rows(
    db: Session,
    *product_states: Any,
) -> List[ListingFacetCache]:
    states = [p for p in product_states if p is not None]
    if not states:
        return []
    rows = (
        db.query(ListingFacetCache)
        .filter(
            ListingFacetCache.scope_type == SCOPE_SEARCH_Q,
            ListingFacetCache.is_enabled.is_(True),
        )
        .all()
    )
    related: List[ListingFacetCache] = []
    for row in rows:
        keyword = row.display_label or row.scope_key
        if any(product_matches_search_keyword(state, keyword) for state in states):
            related.append(row)
    return related


def _cluster_cat_ids(db: Session, cluster_id: int) -> List[int]:
    return [
        c.id
        for c in db.query(Category.id).filter(
            Category.seo_cluster_id == cluster_id, Category.level == 3
        )
    ]


def is_base_facet_request(
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> bool:
    return not any(
        [
            min_price is not None,
            max_price is not None,
            (filter_size or "").strip(),
            (filter_color or "").strip(),
            (filter_style_tag or "").strip(),
        ]
    )


def _has_non_cacheable_listing_dims(
    *,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
) -> bool:
    return any(
        str(v or "").strip()
        for v in (
            shop_name,
            shop_id,
            style,
            shop_name_chinese,
            chinese_name,
            pro_lower_price,
            pro_high_price,
        )
    )


def resolve_facet_scope(
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
) -> Optional[Tuple[str, str, str]]:
    """Trả (scope_type, scope_key, display_label) hoặc None nếu không cache."""
    if _has_non_cacheable_listing_dims(
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
    ):
        return None

    from app.crud.product import normalize_search_query

    raw_q = (q or "").strip()
    if raw_q:
        normalized = normalize_search_query(raw_q)
        if not normalized:
            return None
        return SCOPE_SEARCH_Q, normalized.lower(), normalized

    c1 = (category or "").strip()
    if not c1:
        return None
    c2 = (subcategory or "").strip()
    c3 = (sub_subcategory or "").strip()
    if c3:
        key = f"{c1.lower()}|{c2.lower()}|{c3.lower()}"
        return SCOPE_CATEGORY_L3, key, f"{c1} / {c2} / {c3}"
    if c2:
        key = f"{c1.lower()}|{c2.lower()}"
        return SCOPE_CATEGORY_L2, key, f"{c1} / {c2}"
    return SCOPE_CATEGORY_L1, c1.lower(), c1


def _should_persist_scope(scope_type: str, product_count: int, is_manual: bool) -> bool:
    if scope_type in (SCOPE_CATEGORY_L1, SCOPE_CATEGORY_L2, SCOPE_CATEGORY_L3):
        return True
    if is_manual:
        return True
    return product_count >= MIN_AUTO_CACHE_PRODUCT_COUNT


def try_get_cached_facets(
    db: Session,
    scope_type: str,
    scope_key: str,
) -> Optional[Dict[str, Any]]:
    row = facet_cache_crud.get_by_scope(db, scope_type, scope_key)
    if not row or not row.is_enabled or row.is_stale:
        return None
    return facet_cache_crud.row_to_facets(row)


def count_products_for_scope(
    db: Session,
    scope_type: str,
    scope_key: str,
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
) -> int:
    if scope_type == SCOPE_SEARCH_Q:
        from app.crud.product import apply_product_search_word_filters, normalize_search_query

        normalized = normalize_search_query(q or scope_key)
        words = [w.strip() for w in normalized.split() if w.strip()]
        if not words:
            return 0
        query = db.query(Product).filter(Product.is_active.is_(True))
        query = apply_product_search_word_filters(query, words)
        return query.count()

    if scope_type == SCOPE_SEO_CLUSTER:
        from sqlalchemy import func as sql_func

        cluster = (
            db.query(SeoCluster)
            .filter(sql_func.lower(SeoCluster.slug) == scope_key.lower())
            .first()
        )
        if not cluster:
            return 0
        cat_ids = _cluster_cat_ids(db, cluster.id)
        if not cat_ids:
            return 0
        return (
            db.query(Product)
            .filter(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
            .count()
        )

    from app.crud.product import count_products_for_category_path

    parts = scope_key.split("|")
    c1 = parts[0] if parts else (category or "")
    c2 = parts[1] if len(parts) > 1 else (subcategory or None)
    c3 = parts[2] if len(parts) > 2 else (sub_subcategory or None)
    if scope_type == SCOPE_CATEGORY_L1:
        return count_products_for_category_path(db, c1)
    if scope_type == SCOPE_CATEGORY_L2:
        return count_products_for_category_path(db, c1, c2)
    return count_products_for_category_path(db, c1, c2, c3)


def maybe_cache_listing_facets(db: Session, *, facets: Dict[str, Any], **listing_kwargs) -> None:
    """Lưu facets gốc vào DB nếu đủ điều kiện."""
    if not is_base_facet_request(
        min_price=listing_kwargs.get("min_price"),
        max_price=listing_kwargs.get("max_price"),
        filter_size=listing_kwargs.get("filter_size"),
        filter_color=listing_kwargs.get("filter_color"),
        filter_style_tag=listing_kwargs.get("filter_style_tag"),
    ):
        return
    scope = resolve_facet_scope(
        q=listing_kwargs.get("q"),
        category=listing_kwargs.get("category"),
        subcategory=listing_kwargs.get("subcategory"),
        sub_subcategory=listing_kwargs.get("sub_subcategory"),
        shop_name=listing_kwargs.get("shop_name"),
        shop_id=listing_kwargs.get("shop_id"),
        style=listing_kwargs.get("style"),
        shop_name_chinese=listing_kwargs.get("shop_name_chinese"),
        chinese_name=listing_kwargs.get("chinese_name"),
        pro_lower_price=listing_kwargs.get("pro_lower_price"),
        pro_high_price=listing_kwargs.get("pro_high_price"),
    )
    if not scope:
        return
    product_count = count_products_for_scope(
        db,
        scope[0],
        scope[1],
        q=listing_kwargs.get("q"),
        category=listing_kwargs.get("category"),
        subcategory=listing_kwargs.get("subcategory"),
        sub_subcategory=listing_kwargs.get("sub_subcategory"),
    )
    _maybe_save_facets(
        db,
        scope_type=scope[0],
        scope_key=scope[1],
        display_label=scope[2],
        facets=facets,
        product_count=product_count,
        is_manual=False,
    )


def try_read_cached_listing_facets(db: Session, **listing_kwargs) -> Optional[Dict[str, Any]]:
    if not is_base_facet_request(
        min_price=listing_kwargs.get("min_price"),
        max_price=listing_kwargs.get("max_price"),
        filter_size=listing_kwargs.get("filter_size"),
        filter_color=listing_kwargs.get("filter_color"),
        filter_style_tag=listing_kwargs.get("filter_style_tag"),
    ):
        return None
    scope = resolve_facet_scope(
        q=listing_kwargs.get("q"),
        category=listing_kwargs.get("category"),
        subcategory=listing_kwargs.get("subcategory"),
        sub_subcategory=listing_kwargs.get("sub_subcategory"),
        shop_name=listing_kwargs.get("shop_name"),
        shop_id=listing_kwargs.get("shop_id"),
        style=listing_kwargs.get("style"),
        shop_name_chinese=listing_kwargs.get("shop_name_chinese"),
        chinese_name=listing_kwargs.get("chinese_name"),
        pro_lower_price=listing_kwargs.get("pro_lower_price"),
        pro_high_price=listing_kwargs.get("pro_high_price"),
    )
    if not scope:
        return None
    return try_get_cached_facets(db, scope[0], scope[1])


def get_seo_cluster_facets_with_cache(
    db: Session,
    slug: str,
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> Dict[str, Any]:
    from app.crud import product as product_crud

    slug_norm = (slug or "").strip().lower()
    if is_base_facet_request(
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    ):
        cached = try_get_cached_facets(db, SCOPE_SEO_CLUSTER, slug_norm)
        if cached is not None:
            return cached

    cluster = db.query(SeoCluster).filter(SeoCluster.slug == slug).first()
    if not cluster:
        return {"sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}

    cat_ids = _cluster_cat_ids(db, cluster.id)
    if not cat_ids:
        return {"sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}

    base = db.query(Product).filter(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
    facets = product_crud.build_dependent_product_facets(
        base,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    )

    if is_base_facet_request(
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    ):
        product_count = base.count()
        _maybe_save_facets(
            db,
            scope_type=SCOPE_SEO_CLUSTER,
            scope_key=slug_norm,
            display_label=cluster.name or slug,
            facets=facets,
            product_count=product_count,
            is_manual=False,
        )
    return facets


def _maybe_save_facets(
    db: Session,
    *,
    scope_type: str,
    scope_key: str,
    display_label: str,
    facets: Dict[str, Any],
    product_count: int,
    is_manual: bool,
) -> Optional[ListingFacetCache]:
    if not _should_persist_scope(scope_type, product_count, is_manual):
        return None
    try:
        return facet_cache_crud.upsert_facet_cache(
            db,
            scope_type=scope_type,
            scope_key=scope_key,
            display_label=display_label,
            facets=facets,
            product_count=product_count,
            is_manual=is_manual,
        )
    except Exception as exc:
        logger.warning("Không lưu listing facet cache (%s/%s): %s", scope_type, scope_key, exc)
        return None


def rebuild_category_scope(
    db: Session,
    *,
    category: str,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
) -> Optional[ListingFacetCache]:
    scope = resolve_facet_scope(
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
    )
    if not scope:
        return None
    from app.crud.product import get_product_listing_facets

    facets = get_product_listing_facets(
        db,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        is_active=True,
        skip_cache=True,
    )
    from app.crud.product import count_products_for_category_path

    c1 = (category or "").strip()
    c2 = (subcategory or "").strip() or None
    c3 = (sub_subcategory or "").strip() or None
    product_count = count_products_for_category_path(db, c1, c2, c3)
    existing = facet_cache_crud.get_by_scope(db, scope[0], scope[1])
    is_manual = bool(existing.is_manual) if existing else False
    return facet_cache_crud.upsert_facet_cache(
        db,
        scope_type=scope[0],
        scope_key=scope[1],
        display_label=scope[2],
        facets=facets,
        product_count=product_count,
        is_manual=is_manual,
    )


def rebuild_search_scope(db: Session, keyword: str, *, is_manual: bool = False) -> Optional[ListingFacetCache]:
    from app.crud.product import get_product_listing_facets, normalize_search_query

    normalized = normalize_search_query((keyword or "").strip())
    if not normalized:
        return None
    scope_key = normalized.lower()
    facets = get_product_listing_facets(db, q=normalized, is_active=True, skip_cache=True)
    from app.crud.product import apply_product_search_word_filters

    words = [w.strip() for w in normalized.split() if w.strip()]
    q = db.query(Product).filter(Product.is_active.is_(True))
    q = apply_product_search_word_filters(q, words)
    product_count = q.count()
    if not _should_persist_scope(SCOPE_SEARCH_Q, product_count, is_manual):
        row = facet_cache_crud.get_by_scope(db, SCOPE_SEARCH_Q, scope_key)
        if row and not row.is_manual:
            facet_cache_crud.delete_row(db, row.id)
        return None
    return facet_cache_crud.upsert_facet_cache(
        db,
        scope_type=SCOPE_SEARCH_Q,
        scope_key=scope_key,
        display_label=normalized,
        facets=facets,
        product_count=product_count,
        is_manual=is_manual,
    )


def rebuild_seo_cluster_scope(db: Session, slug: str) -> Optional[ListingFacetCache]:
    from app.crud import product as product_crud

    slug_norm = (slug or "").strip().lower()
    cluster = db.query(SeoCluster).filter(SeoCluster.slug == slug).first()
    if not cluster:
        return None
    cat_ids = _cluster_cat_ids(db, cluster.id)
    if not cat_ids:
        return None
    base = db.query(Product).filter(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
    product_count = base.count()
    if product_count < MIN_AUTO_CACHE_PRODUCT_COUNT:
        row = facet_cache_crud.get_by_scope(db, SCOPE_SEO_CLUSTER, slug_norm)
        if row and not row.is_manual:
            facet_cache_crud.delete_row(db, row.id)
        return None
    facets = product_crud.build_dependent_product_facets(base)
    existing = facet_cache_crud.get_by_scope(db, SCOPE_SEO_CLUSTER, slug_norm)
    is_manual = bool(existing.is_manual) if existing else False
    return facet_cache_crud.upsert_facet_cache(
        db,
        scope_type=SCOPE_SEO_CLUSTER,
        scope_key=slug_norm,
        display_label=cluster.name or slug,
        facets=facets,
        product_count=product_count,
        is_manual=is_manual,
    )


def iter_distinct_category_paths(db: Session) -> List[Tuple[str, Optional[str], Optional[str]]]:
    rows = (
        db.query(Product.category, Product.subcategory, Product.sub_subcategory)
        .filter(Product.is_active.is_(True), Product.category.isnot(None))
        .distinct()
        .all()
    )
    seen_l1: set = set()
    seen_l2: set = set()
    seen_l3: set = set()
    out: List[Tuple[str, Optional[str], Optional[str]]] = []

    for c1, c2, c3 in rows:
        c1s = (c1 or "").strip()
        if not c1s:
            continue
        k1 = c1s.lower()
        if k1 not in seen_l1:
            seen_l1.add(k1)
            out.append((c1s, None, None))
        c2s = (c2 or "").strip()
        if c2s:
            k2 = f"{k1}|{c2s.lower()}"
            if k2 not in seen_l2:
                seen_l2.add(k2)
                out.append((c1s, c2s, None))
        c3s = (c3 or "").strip()
        if c2s and c3s:
            k3 = f"{k1}|{c2s.lower()}|{c3s.lower()}"
            if k3 not in seen_l3:
                seen_l3.add(k3)
                out.append((c1s, c2s, c3s))
    return out


def rebuild_all_category_caches(db: Session) -> int:
    count = 0
    for c1, c2, c3 in iter_distinct_category_paths(db):
        try:
            rebuild_category_scope(db, category=c1, subcategory=c2, sub_subcategory=c3)
            count += 1
        except Exception as exc:
            logger.warning("Rebuild category facet cache failed (%s/%s/%s): %s", c1, c2, c3, exc)
    return count


def rebuild_all_search_caches(db: Session) -> int:
    rows = (
        db.query(ListingFacetCache)
        .filter(ListingFacetCache.scope_type == SCOPE_SEARCH_Q)
        .all()
    )
    count = 0
    for row in rows:
        try:
            rebuild_search_scope(db, row.display_label or row.scope_key, is_manual=row.is_manual)
            count += 1
        except Exception as exc:
            logger.warning("Rebuild search facet cache failed (%s): %s", row.scope_key, exc)
    return count


def rebuild_all_seo_cluster_caches(db: Session) -> int:
    clusters = db.query(SeoCluster).order_by(SeoCluster.slug.asc()).all()
    count = 0
    for cluster in clusters:
        try:
            if rebuild_seo_cluster_scope(db, cluster.slug):
                count += 1
        except Exception as exc:
            logger.warning("Rebuild SEO cluster facet cache failed (%s): %s", cluster.slug, exc)
    return count


def _category_paths_for_product_change(
    product: Product,
    *,
    old_category: Optional[str] = None,
    old_subcategory: Optional[str] = None,
    old_sub_subcategory: Optional[str] = None,
) -> List[Tuple[str, Optional[str], Optional[str]]]:
    paths: List[Tuple[str, Optional[str], Optional[str]]] = []
    for c1, c2, c3 in (
        (product.category, product.subcategory, product.sub_subcategory),
        (old_category, old_subcategory, old_sub_subcategory),
    ):
        c1s = (c1 or "").strip()
        if not c1s:
            continue
        paths.append((c1s, (c2 or "").strip() or None, (c3 or "").strip() or None))
        c2s = (c2 or "").strip()
        if c2s:
            paths.append((c1s, c2s, None))
        paths.append((c1s, None, None))
    return paths


def _cluster_slugs_for_category_id(db: Session, category_id: Optional[int]) -> List[str]:
    if not category_id:
        return []
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat or not cat.seo_cluster_id:
        return []
    cluster = db.query(SeoCluster).filter(SeoCluster.id == cat.seo_cluster_id).first()
    if not cluster:
        return []
    return [cluster.slug]


def refresh_caches_after_product_change(
    db: Session,
    product: Product,
    *,
    old_category: Optional[str] = None,
    old_subcategory: Optional[str] = None,
    old_sub_subcategory: Optional[str] = None,
    old_category_id: Optional[int] = None,
    previous_product: Optional[Any] = None,
) -> None:
    """Rebuild cache danh mục / SEO cluster / từ khóa tìm kiếm liên quan SP."""
    refresh_caches_after_products_change(
        db,
        [product],
        old_category=old_category,
        old_subcategory=old_subcategory,
        old_sub_subcategory=old_sub_subcategory,
        old_category_id=old_category_id,
        previous_products=[previous_product] if previous_product is not None else None,
    )


def refresh_caches_after_products_change(
    db: Session,
    products: List[Any],
    *,
    old_category: Optional[str] = None,
    old_subcategory: Optional[str] = None,
    old_sub_subcategory: Optional[str] = None,
    old_category_id: Optional[int] = None,
    previous_products: Optional[List[Any]] = None,
) -> None:
    """Rebuild cache liên quan một hoặc nhiều SP (dedupe phạm vi rebuild)."""
    if not products:
        return

    paths: List[Tuple[str, Optional[str], Optional[str]]] = []
    for product in products:
        paths.extend(
            _category_paths_for_product_change(
                product,
                old_category=old_category,
                old_subcategory=old_subcategory,
                old_sub_subcategory=old_sub_subcategory,
            )
        )

    seen_scopes: set = set()
    for c1, c2, c3 in paths:
        scope = resolve_facet_scope(category=c1, subcategory=c2, sub_subcategory=c3)
        if not scope or scope[1] in seen_scopes:
            continue
        seen_scopes.add(scope[1])
        try:
            rebuild_category_scope(db, category=c1, subcategory=c2, sub_subcategory=c3)
        except Exception as exc:
            logger.warning("Refresh category facet cache after product change failed: %s", exc)

    slugs: set = set()
    for product in products:
        slugs.update(_cluster_slugs_for_category_id(db, getattr(product, "category_id", None)))
    if old_category_id:
        slugs.update(_cluster_slugs_for_category_id(db, old_category_id))

    for slug in slugs:
        try:
            rebuild_seo_cluster_scope(db, slug)
        except Exception as exc:
            logger.warning("Refresh SEO cluster facet cache failed (%s): %s", slug, exc)

    search_states: List[Any] = list(products)
    if previous_products:
        search_states.extend(p for p in previous_products if p is not None)

    seen_search: set = set()
    for row in iter_related_search_cache_rows(db, *search_states):
        if row.scope_key in seen_search:
            continue
        seen_search.add(row.scope_key)
        try:
            rebuild_search_scope(
                db,
                row.display_label or row.scope_key,
                is_manual=bool(row.is_manual),
            )
        except Exception as exc:
            logger.warning("Refresh search facet cache failed (%s): %s", row.scope_key, exc)


def refresh_caches_after_bulk_import(db: Session) -> None:
    try:
        rebuild_all_category_caches(db)
        facet_cache_crud.mark_stale_by_types(db, (SCOPE_SEARCH_Q,))
        rebuild_all_search_caches(db)
        rebuild_all_seo_cluster_caches(db)
    except Exception as exc:
        logger.warning("Refresh facet caches after bulk import failed: %s", exc)
