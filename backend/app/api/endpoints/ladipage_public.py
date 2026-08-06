# backend/app/api/endpoints/ladipage_public.py - Trang public Ladipage (/lp/<slug>)
"""Chỉ trả ladipage đã publish. Mount tại /api/v1/ladipages (xem main.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ladipage import Ladipage
from app.schemas.ladipage import (
    LadipagePublicResponse,
    LadipageSectionResponse,
    LadipageSitemapItem,
    LadipageSitemapResponse,
)
from app.services.ladipage_ai_service import resolve_products_for_ladipage
from app.services.ladipage_cleanup import (
    get_published_single_product_ladipage_slug,
    is_single_product_ladipage_for_product,
)
from app.services.ladipage_public_url import is_single_product_ladipage, resolve_ladipage_public_path

router = APIRouter()


def _public_ladipage_response(db: Session, lp: Ladipage) -> LadipagePublicResponse:
    resolved = [p.id for p in resolve_products_for_ladipage(db, lp)]
    sections = [
        LadipageSectionResponse.model_validate(s)
        for s in sorted(lp.sections, key=lambda s: s.order_index)
        if s.status == "ready"
    ]
    return LadipagePublicResponse(
        id=lp.id,
        slug=lp.slug,
        title=lp.title,
        meta_title=lp.meta_title or lp.title,
        meta_description=lp.meta_description,
        sections=sections,
        resolved_product_ids=resolved,
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
