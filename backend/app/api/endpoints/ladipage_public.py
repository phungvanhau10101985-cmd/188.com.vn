# backend/app/api/endpoints/ladipage_public.py - Trang public Ladipage (/lp/<slug>)
"""Chỉ trả ladipage đã publish. Mount tại /api/v1/ladipages (xem main.py)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.category import Category
from app.models.ladipage import Ladipage
from app.models.seo_cluster import SeoCluster
from app.schemas.ladipage import (
    LadipagePublicResponse,
    LadipageRelatedItem,
    LadipageRelatedResponse,
    LadipageSectionResponse,
    LadipageSitemapItem,
    LadipageSitemapResponse,
)
from app.services.ladipage_ai_service import resolve_products_for_ladipage
from app.services.ladipage_cleanup import (
    get_published_single_product_ladipage_slug,
    is_single_product_ladipage_for_product,
)
from app.services.ladipage_public_url import is_single_product_ladipage
from app.services.ladipage_seo_strategy import (
    list_related_ladipages_for_categories,
    resolve_ladipage_category_competitor,
)

router = APIRouter()


def _public_ladipage_response(db: Session, lp: Ladipage) -> LadipagePublicResponse:
    resolved = [p.id for p in resolve_products_for_ladipage(db, lp)]
    sections = [
        LadipageSectionResponse.model_validate(s)
        for s in sorted(lp.sections, key=lambda s: s.order_index)
        if s.status == "ready"
    ]
    # Danh mục liên quan: category_id thật (ladipage danh mục) hoặc danh mục chiếm đa số
    # trong SP đã chọn (ladipage nhiều SP) — dùng cho breadcrumb + link "xem toàn bộ danh mục".
    competitor = resolve_ladipage_category_competitor(db, lp, resolved)
    return LadipagePublicResponse(
        id=lp.id,
        slug=lp.slug,
        title=lp.title,
        meta_title=lp.meta_title or lp.title,
        meta_description=lp.meta_description,
        material_filter=lp.material_filter,
        category_id=competitor.get("category_id"),
        category_name=competitor.get("category_name"),
        category_catalog_path=competitor.get("catalog_path"),
        category_seo_path=competitor.get("seo_path"),
        sections=sections,
        resolved_product_ids=resolved,
    )


def _related_item(lp: Ladipage) -> LadipageRelatedItem:
    return LadipageRelatedItem(
        id=lp.id,
        slug=lp.slug,
        title=lp.title,
        material_filter=lp.material_filter,
        path=f"/lp/{lp.slug}",
        meta_title=lp.meta_title,
    )


@router.get("/public/sitemap", response_model=LadipageSitemapResponse)
def list_published_ladipages_for_sitemap(db: Session = Depends(get_db)):
    """Danh sách slug ladipage đã publish — bỏ qua ladipage 1 SP (dùng URL sản phẩm)."""
    rows = (
        db.query(Ladipage)
        .filter(Ladipage.status == "published")
        .order_by(Ladipage.published_at.desc(), Ladipage.updated_at.desc())
        .all()
    )
    return LadipageSitemapResponse(
        items=[
            LadipageSitemapItem(slug=lp.slug, updated_at=lp.updated_at, published_at=lp.published_at)
            for lp in rows
            if not is_single_product_ladipage(lp)
        ]
    )


@router.get("/public/related", response_model=LadipageRelatedResponse)
def list_related_published_ladipages(
    category_id: Optional[int] = Query(None, ge=1),
    category_path: Optional[str] = Query(
        None,
        description="full_slug danh mục, vd giay-dep-nam/.../oxford-nam",
    ),
    cluster_slug: Optional[str] = Query(None, description="slug SEO cluster /c/{slug}"),
    limit: int = Query(8, ge=1, le=24),
    exclude_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """Ladipage danh mục đã publish — dùng link chéo từ trang danh mục/cluster."""
    cat_ids: List[int] = []
    if category_id:
        cat_ids = [int(category_id)]
    elif category_path and category_path.strip():
        path = category_path.strip().strip("/").lower()
        cat = db.query(Category).filter(Category.full_slug == path).first()
        if not cat:
            # thử khớp không lower
            cat = db.query(Category).filter(Category.full_slug == category_path.strip().strip("/")).first()
        if cat:
            cat_ids = [cat.id]
    elif cluster_slug and cluster_slug.strip():
        cluster = db.query(SeoCluster).filter(SeoCluster.slug == cluster_slug.strip()).first()
        if cluster:
            cat_ids = [
                int(row[0])
                for row in db.query(Category.id)
                .filter(Category.seo_cluster_id == cluster.id, Category.level == 3)
                .all()
            ]
    else:
        raise HTTPException(
            status_code=400,
            detail="Cần category_id hoặc category_path hoặc cluster_slug",
        )

    rows = list_related_ladipages_for_categories(
        db,
        category_ids=cat_ids,
        limit=limit,
        exclude_ladipage_id=exclude_id,
    )
    return LadipageRelatedResponse(items=[_related_item(lp) for lp in rows])


@router.get("/public/by-product/{product_db_id}", response_model=LadipagePublicResponse)
def get_published_ladipage_for_product(product_db_id: int, db: Session = Depends(get_db)):
    """Ladipage 1 SP đã publish — nội dung bổ sung cho PDP ``/products/...``."""
    slug = get_published_single_product_ladipage_slug(db, product_db_id)
    if not slug:
        raise HTTPException(status_code=404, detail="Không có ladipage publish cho sản phẩm này")
    lp = db.query(Ladipage).filter(Ladipage.slug == slug).first()
    if not lp or lp.status != "published":
        raise HTTPException(status_code=404, detail="Không có ladipage publish cho sản phẩm này")
    if not is_single_product_ladipage_for_product(lp, product_db_id):
        raise HTTPException(status_code=404, detail="Không có ladipage publish cho sản phẩm này")
    return _public_ladipage_response(db, lp)


@router.get("/public/{slug}", response_model=LadipagePublicResponse)
def get_public_ladipage(slug: str, db: Session = Depends(get_db)):
    lp = db.query(Ladipage).filter(Ladipage.slug == slug).first()
    if not lp or lp.status != "published":
        raise HTTPException(status_code=404, detail="Không tìm thấy trang")
    return _public_ladipage_response(db, lp)
