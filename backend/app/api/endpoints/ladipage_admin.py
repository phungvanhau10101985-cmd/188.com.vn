# backend/app/api/endpoints/ladipage_admin.py - Quản trị Ladipage AI
"""
CRUD + sinh nội dung AI (DeepSeek text + Gemini ảnh chất liệu) cho Ladipage. Mount tại /api/v1/admin/ladipages (xem main.py).
Quyền: module_key "ladipage" (xem app.core.admin_permissions.ALLOWED_MODULE_KEYS).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_module_permission, require_module_permission_with_destructive_step_up
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.category import Category
from app.models.ladipage import Ladipage, LadipageSection
from app.schemas.ladipage import (
    LadipageCreate,
    LadipageDetailResponse,
    LadipageListResponse,
    LadipageResponse,
    LadipageSeoResponse,
    LadipageSectionResponse,
    LadipageUpdate,
    SectionManualUpdateRequest,
    SectionRegenerateRequest,
)
from app.services import bunny_storage
from app.services.ladipage_ai_service import (
    build_fixed_sections_plan,
    generate_and_save_ladipage_seo,
    generate_or_regenerate_section,
    resolve_products_for_ladipage,
)
from app.services.ladipage_public_url import resolve_ladipage_public_path
from app.utils.slug import create_slug

logger = logging.getLogger(__name__)
router = APIRouter()

MODULE_KEY = "ladipage"


def _unique_slug(db: Session, base: str, *, exclude_id: Optional[int] = None) -> str:
    base_slug = create_slug(base) or "ladipage"
    slug = base_slug
    n = 2
    while True:
        q = db.query(Ladipage.id).filter(Ladipage.slug == slug)
        if exclude_id:
            q = q.filter(Ladipage.id != exclude_id)
        if not q.first():
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _to_response(db: Session, lp: Ladipage) -> LadipageResponse:
    return LadipageResponse(
        id=lp.id,
        slug=lp.slug,
        title=lp.title,
        status=lp.status,
        source_type=lp.source_type,
        category_id=lp.category_id,
        category_name=lp.category_rel.name if lp.category_rel else None,
        product_ids=list(lp.product_ids or []),
        admin_brief=lp.admin_brief,
        include_material=lp.include_material,
        include_faq=lp.include_faq,
        products_limit=lp.products_limit,
        meta_title=lp.meta_title,
        meta_description=lp.meta_description,
        created_at=lp.created_at,
        updated_at=lp.updated_at,
        published_at=lp.published_at,
        public_url=resolve_ladipage_public_path(db, lp),
    )


def _to_detail_response(db: Session, lp: Ladipage) -> LadipageDetailResponse:
    base = _to_response(db, lp).model_dump()
    resolved = [p.id for p in resolve_products_for_ladipage(db, lp)]
    sections = [
        LadipageSectionResponse.model_validate(s) for s in sorted(lp.sections, key=lambda s: s.order_index)
    ]
    return LadipageDetailResponse(**base, sections=sections, resolved_product_ids=resolved)


def _get_ladipage_or_404(db: Session, ladipage_id: int) -> Ladipage:
    lp = db.query(Ladipage).filter(Ladipage.id == ladipage_id).first()
    if not lp:
        raise HTTPException(status_code=404, detail="Không tìm thấy ladipage")
    return lp


def _get_section_or_404(db: Session, ladipage_id: int, section_id: int) -> LadipageSection:
    section = (
        db.query(LadipageSection)
        .filter(LadipageSection.id == section_id, LadipageSection.ladipage_id == ladipage_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Không tìm thấy phần nội dung")
    return section


def _collect_section_image_urls(lp: Ladipage) -> List[str]:
    urls: List[str] = []
    for s in lp.sections:
        data = s.data or {}
        url = data.get("image_url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def _hero_copy_from_ladipage(lp: Ladipage) -> tuple[Optional[str], Optional[str]]:
    for section in sorted(lp.sections, key=lambda s: s.order_index):
        if section.section_type != "hero":
            continue
        data = section.data or {}
        headline = str(data.get("headline") or "").strip() or None
        subheadline = str(data.get("subheadline") or "").strip() or None
        return headline, subheadline
    return None, None


def _ladipage_needs_seo(lp: Ladipage) -> bool:
    return not (lp.meta_title or "").strip() or not (lp.meta_description or "").strip()


def _try_auto_generate_ladipage_seo(db: Session, lp: Ladipage) -> None:
    """Tự sinh meta title/description còn thiếu khi các section AI đã xong."""
    db.refresh(lp)
    if not _ladipage_needs_seo(lp):
        return
    sections = (
        db.query(LadipageSection)
        .filter(LadipageSection.ladipage_id == lp.id)
        .order_by(LadipageSection.order_index)
        .all()
    )
    pending_ai = [
        s for s in sections if s.section_type != "products_grid" and s.status == "pending"
    ]
    if pending_ai:
        return
    headline, subheadline = None, None
    for section in sections:
        if section.section_type != "hero":
            continue
        data = section.data or {}
        headline = str(data.get("headline") or "").strip() or None
        subheadline = str(data.get("subheadline") or "").strip() or None
        break
    if not headline and not (lp.title or "").strip():
        return
    try:
        generate_and_save_ladipage_seo(
            db,
            lp,
            hero_headline=headline,
            hero_subheadline=subheadline,
            only_missing=True,
        )
    except Exception as exc:
        logger.warning("Ladipage %s: auto SEO sau section thất bại: %s", lp.id, exc)


@router.get("", response_model=LadipageListResponse, include_in_schema=False)
@router.get("/", response_model=LadipageListResponse)
def list_ladipages(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    q = db.query(Ladipage)
    if status_filter in ("draft", "published"):
        q = q.filter(Ladipage.status == status_filter)
    total = q.count()
    rows = q.order_by(Ladipage.id.desc()).offset(skip).limit(limit).all()
    return LadipageListResponse(total=total, items=[_to_response(db, r) for r in rows])


@router.post("", response_model=LadipageDetailResponse, include_in_schema=False)
@router.post("/", response_model=LadipageDetailResponse)
def create_ladipage(
    payload: LadipageCreate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    if payload.source_type == "category":
        if not payload.category_id:
            raise HTTPException(status_code=400, detail="Cần chọn danh mục")
        cat = db.query(Category).filter(Category.id == payload.category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Không tìm thấy danh mục")
    elif payload.source_type == "products":
        if not payload.product_ids:
            raise HTTPException(status_code=400, detail="Cần chọn ít nhất 1 sản phẩm")
    else:
        raise HTTPException(status_code=400, detail="source_type không hợp lệ")

    slug = _unique_slug(db, payload.title)
    lp = Ladipage(
        slug=slug,
        title=payload.title.strip(),
        status="draft",
        source_type=payload.source_type,
        category_id=payload.category_id if payload.source_type == "category" else None,
        product_ids=payload.product_ids if payload.source_type == "products" else [],
        admin_brief=(payload.admin_brief or "").strip(),
        include_material=payload.include_material,
        include_faq=payload.include_faq,
        products_limit=payload.products_limit,
        created_by=admin.id,
    )
    db.add(lp)
    db.flush()

    plan = build_fixed_sections_plan(payload.include_material, payload.include_faq)
    is_single_product = (
        payload.source_type == "products"
        and len(payload.product_ids or []) == 1
    )
    material_source = payload.material_image_source if is_single_product else "ai"
    for idx, section_type in enumerate(plan):
        section_data: Dict[str, Any] = {}
        if section_type == "material" and is_single_product:
            section_data["image_source"] = material_source if material_source in ("ai", "product") else "product"
        db.add(
            LadipageSection(
                ladipage_id=lp.id,
                section_type=section_type,
                order_index=idx,
                status="ready" if section_type == "products_grid" else "pending",
                data=section_data,
            )
        )
    db.commit()
    db.refresh(lp)
    return _to_detail_response(db, lp)


@router.get("/{ladipage_id}", response_model=LadipageDetailResponse)
def get_ladipage(
    ladipage_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    lp = _get_ladipage_or_404(db, ladipage_id)
    return _to_detail_response(db, lp)


@router.patch("/{ladipage_id}", response_model=LadipageDetailResponse)
def update_ladipage(
    ladipage_id: int,
    payload: LadipageUpdate,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    lp = _get_ladipage_or_404(db, ladipage_id)

    if payload.title is not None:
        lp.title = payload.title.strip()
    if payload.slug is not None and payload.slug.strip() and payload.slug.strip() != lp.slug:
        new_slug = _unique_slug(db, payload.slug.strip(), exclude_id=lp.id)
        lp.slug = new_slug
    if payload.admin_brief is not None:
        lp.admin_brief = payload.admin_brief.strip()
    if payload.meta_title is not None:
        lp.meta_title = payload.meta_title.strip() or None
    if payload.meta_description is not None:
        lp.meta_description = payload.meta_description.strip() or None
    if payload.products_limit is not None:
        lp.products_limit = payload.products_limit
    if payload.product_ids is not None and lp.source_type == "products":
        lp.product_ids = payload.product_ids
    if payload.status is not None and payload.status != lp.status:
        if payload.status == "published":
            lp.published_at = datetime.now(timezone.utc)
            if _ladipage_needs_seo(lp):
                headline, subheadline = _hero_copy_from_ladipage(lp)
                try:
                    generate_and_save_ladipage_seo(
                        db,
                        lp,
                        hero_headline=headline,
                        hero_subheadline=subheadline,
                        only_missing=True,
                    )
                except Exception as exc:
                    logger.warning("Ladipage %s: auto SEO khi publish thất bại: %s", ladipage_id, exc)
        lp.status = payload.status

    db.commit()
    db.refresh(lp)
    return _to_detail_response(db, lp)


@router.post("/{ladipage_id}/generate-seo", response_model=LadipageDetailResponse)
def generate_ladipage_seo_endpoint(
    ladipage_id: int,
    only_missing: bool = Query(False, alias="only_missing"),
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    """Sinh meta title/description bằng DeepSeek từ nội dung ladipage và lưu vào DB."""
    lp = _get_ladipage_or_404(db, ladipage_id)
    headline, subheadline = _hero_copy_from_ladipage(lp)
    try:
        generate_and_save_ladipage_seo(
            db,
            lp,
            hero_headline=headline,
            hero_subheadline=subheadline,
            only_missing=only_missing,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI tạo SEO thất bại: {exc}") from exc
    return _to_detail_response(db, lp)


@router.delete("/{ladipage_id}", response_model=dict)
def delete_ladipage(
    ladipage_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission_with_destructive_step_up(MODULE_KEY, need="delete")),
):
    lp = _get_ladipage_or_404(db, ladipage_id)
    image_urls = _collect_section_image_urls(lp)
    db.delete(lp)
    db.commit()
    try:
        if image_urls:
            bunny_storage.delete_bunny_storage_objects_for_urls(image_urls)
    except Exception:
        logger.warning("Ladipage %s: dọn ảnh Bunny thất bại (bỏ qua)", ladipage_id, exc_info=True)
    return {"ok": True, "deleted_id": ladipage_id}


@router.post("/{ladipage_id}/sections/{section_id}/generate", response_model=LadipageSectionResponse)
def generate_section(
    ladipage_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    lp = _get_ladipage_or_404(db, ladipage_id)
    section = _get_section_or_404(db, ladipage_id, section_id)
    try:
        new_data = generate_or_regenerate_section(db, lp, section, target="all")
        section.data = new_data
        section.status = "ready"
        section.error_message = None
    except Exception as exc:
        logger.warning("Ladipage %s section %s generate lỗi: %s", ladipage_id, section_id, exc)
        section.status = "error"
        section.error_message = str(exc)[:2000]
    db.commit()
    db.refresh(section)
    db.refresh(lp)
    if section.status == "ready":
        _try_auto_generate_ladipage_seo(db, lp)
    return LadipageSectionResponse.model_validate(section)


@router.post("/{ladipage_id}/sections/{section_id}/regenerate", response_model=LadipageSectionResponse)
def regenerate_section(
    ladipage_id: int,
    section_id: int,
    payload: SectionRegenerateRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    lp = _get_ladipage_or_404(db, ladipage_id)
    section = _get_section_or_404(db, ladipage_id, section_id)
    try:
        new_data = generate_or_regenerate_section(
            db, lp, section, target=payload.target, custom_prompt=(payload.custom_prompt or "").strip() or None
        )
        section.data = new_data
        section.status = "ready"
        section.error_message = None
    except Exception as exc:
        logger.warning("Ladipage %s section %s regenerate lỗi: %s", ladipage_id, section_id, exc)
        section.status = "error"
        section.error_message = str(exc)[:2000]
        db.commit()
        raise HTTPException(status_code=502, detail=f"AI tạo nội dung thất bại: {exc}")
    db.commit()
    db.refresh(section)
    db.refresh(lp)
    _try_auto_generate_ladipage_seo(db, lp)
    return LadipageSectionResponse.model_validate(section)


@router.patch("/{ladipage_id}/sections/{section_id}", response_model=LadipageSectionResponse)
def update_section_manually(
    ladipage_id: int,
    section_id: int,
    payload: SectionManualUpdateRequest,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(require_module_permission(MODULE_KEY)),
):
    section = _get_section_or_404(db, ladipage_id, section_id)
    merged: Dict[str, Any] = {**(section.data or {}), **(payload.data or {})}
    section.data = merged
    if section.status == "pending":
        section.status = "ready"
    db.commit()
    db.refresh(section)
    return LadipageSectionResponse.model_validate(section)
