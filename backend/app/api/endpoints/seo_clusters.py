# backend/app/api/endpoints/seo_clusters.py
"""
Public endpoints cho SEO landing cluster (`/c/<slug>`).

- GET /api/v1/seo-clusters         : list ngắn (slug + name + product_count) cho sitemap.
- GET /api/v1/seo-clusters/{slug}  : chi tiết cluster (kèm danh sách cat3_ids + sample SP đầu trang).
- GET /api/v1/seo-clusters/{slug}/products?limit=&skip= : danh sách SP của cluster (qua category_id IN cat3_ids).

Cache TTL 60s (singleflight) — endpoint này được Next SSR landing gọi mỗi request.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.category import Category
from app.models.product import Product
from app.models.seo_cluster import SeoCluster
from app.utils.ttl_cache import cache as ttl_cache

router = APIRouter()

_LIST_TTL = 60.0
_DETAIL_TTL = 60.0
_LIST_KEY = "seo_clusters_v1:list"


# ---------- helpers ----------
def _serialize_product_card(p: Product) -> Dict[str, Any]:
    return {
        "id": p.id,
        "product_id": p.product_id,
        "name": p.name,
        "slug": p.slug,
        "main_image": p.main_image,
        "images": p.images or [],
        "price": p.price,
        "pro_lower_price": p.pro_lower_price,
        "pro_high_price": p.pro_high_price,
        "rating_point": p.rating_point,
        "rating_total": p.rating_total,
        "purchases": p.purchases,
        "shop_name": p.shop_name,
        "available": p.available,
        "brand_name": p.brand_name,
    }


def _fetch_clusters_list() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        clusters = (
            db.query(SeoCluster)
            .order_by(SeoCluster.slug)
            .all()
        )
        # Đếm product theo cluster (nhóm theo cat3.seo_cluster_id → category_id)
        counts: Dict[int, int] = {}
        rows = (
            db.query(Category.seo_cluster_id, Product.id)
            .join(Product, Product.category_id == Category.id)
            .filter(Category.level == 3, Category.seo_cluster_id.isnot(None), Product.is_active.is_(True))
            .all()
        )
        for cid, _pid in rows:
            counts[cid] = counts.get(cid, 0) + 1

        return [
            {
                "id": c.id,
                "slug": c.slug,
                "name": c.name,
                "canonical_path": c.canonical_path,
                "index_policy": c.index_policy,
                "product_count": counts.get(c.id, 0),
            }
            for c in clusters
        ]
    finally:
        db.close()


def _fetch_cluster_detail(slug: str, sample_limit: int = 24) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        cluster = db.query(SeoCluster).filter(SeoCluster.slug == slug).first()
        if not cluster:
            raise HTTPException(status_code=404, detail=f"SEO cluster '{slug}' không tồn tại")

        cats = (
            db.query(Category)
            .filter(Category.seo_cluster_id == cluster.id, Category.level == 3)
            .all()
        )
        cat_ids = [c.id for c in cats]
        cat_summaries = [
            {"id": c.id, "name": c.name, "slug": c.slug, "full_slug": c.full_slug}
            for c in cats
        ]

        total = 0
        sample_products: List[Dict[str, Any]] = []
        if cat_ids:
            base = (
                db.query(Product)
                .filter(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
            )
            total = base.count()
            sample_products = [
                _serialize_product_card(p)
                for p in base.order_by(Product.purchases.desc(), Product.rating_point.desc(), Product.id.desc())
                .limit(sample_limit)
                .all()
            ]
        return {
            "id": cluster.id,
            "slug": cluster.slug,
            "name": cluster.name,
            "canonical_path": cluster.canonical_path,
            "index_policy": cluster.index_policy,
            "source": cluster.source,
            "notes": cluster.notes,
            "categories": cat_summaries,
            "product_count": total,
            "products_sample": sample_products,
        }
    finally:
        db.close()


# ---------- routes ----------
@router.get("/")
@router.get("")
def list_seo_clusters() -> List[Dict[str, Any]]:
    """Danh sách cluster (cho sitemap, admin tổng quan)."""
    return ttl_cache.get_or_fetch(_LIST_KEY, _LIST_TTL, _fetch_clusters_list)


@router.get("/{slug}")
def get_seo_cluster(slug: str) -> Dict[str, Any]:
    """
    Chi tiết cluster + sample 24 sản phẩm đầu (để Next render đầu landing nhanh).
    """
    key = f"seo_clusters_v1:detail:{slug}"
    return ttl_cache.get_or_fetch(key, _DETAIL_TTL, lambda: _fetch_cluster_detail(slug))


@router.get("/{slug}/products")
def get_seo_cluster_products(
    slug: str,
    limit: int = Query(48, ge=1, le=200),
    skip: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Phân trang sản phẩm của cluster. Không cache (page-specific) — DB index nhanh.
    """
    cluster = db.query(SeoCluster).filter(SeoCluster.slug == slug).first()
    if not cluster:
        raise HTTPException(status_code=404, detail=f"SEO cluster '{slug}' không tồn tại")

    cat_ids = [
        c.id
        for c in db.query(Category.id).filter(
            Category.seo_cluster_id == cluster.id, Category.level == 3
        )
    ]
    if not cat_ids:
        return {"total": 0, "skip": skip, "limit": limit, "products": []}

    base = (
        db.query(Product)
        .filter(Product.category_id.in_(cat_ids), Product.is_active.is_(True))
    )
    total = base.count()
    products = (
        base.order_by(Product.purchases.desc(), Product.rating_point.desc(), Product.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "products": [_serialize_product_card(p) for p in products],
    }
