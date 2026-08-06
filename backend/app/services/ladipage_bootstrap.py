# backend/app/services/ladipage_bootstrap.py
"""Tạo & sinh nội dung ladipage 1 SP hàng loạt — dùng cho bootstrap catalog."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

from app.models.ladipage import Ladipage, LadipageSection
from app.models.product import Product
from app.services.ladipage_ai_service import (
    build_fixed_sections_plan,
    generate_and_save_ladipage_seo,
    generate_or_regenerate_section,
)
from app.services.ladipage_cleanup import find_single_product_ladipages_for_product
from app.utils.slug import create_slug

logger = logging.getLogger(__name__)


def _unique_ladipage_slug(db: Session, base: str) -> str:
    base_slug = create_slug(base) or "ladipage"
    slug = base_slug
    n = 2
    while db.query(Ladipage.id).filter(Ladipage.slug == slug).first():
        slug = f"{base_slug}-{n}"
        n += 1
    return slug


def product_ids_with_single_ladipage(db: Session) -> Set[int]:
    """products.id đã có ít nhất một ladipage 1 SP (mọi trạng thái)."""
    covered: Set[int] = set()
    for lp in db.query(Ladipage).filter(Ladipage.source_type == "products").all():
        raw = lp.product_ids or []
        if isinstance(raw, list) and len(raw) == 1:
            try:
                covered.add(int(raw[0]))
            except (TypeError, ValueError):
                continue
    return covered


def create_single_product_ladipage_record(
    db: Session,
    product: Product,
    *,
    created_by: Optional[int] = None,
    material_image_source: str = "product",
    include_material: bool = True,
    include_faq: bool = True,
) -> Ladipage:
    """Tạo bản ghi ladipage + sections (chưa gọi AI)."""
    title = (product.name or f"Sản phẩm {product.id}").strip()[:500]
    lp = Ladipage(
        slug=_unique_ladipage_slug(db, title),
        title=title,
        status="draft",
        source_type="products",
        product_ids=[int(product.id)],
        admin_brief="",
        include_material=include_material,
        include_faq=include_faq,
        products_limit=12,
        created_by=created_by,
    )
    db.add(lp)
    db.flush()

    plan = build_fixed_sections_plan(include_material, include_faq)
    for idx, section_type in enumerate(plan):
        section_data: Dict[str, Any] = {}
        if section_type == "material":
            section_data["image_source"] = (
                material_image_source if material_image_source in ("ai", "product") else "product"
            )
        db.add(
            LadipageSection(
                ladipage_id=lp.id,
                section_type=section_type,
                order_index=idx,
                status="ready" if section_type == "products_grid" else "pending",
                data=section_data,
            )
        )
    db.flush()
    db.refresh(lp)
    return lp


def fill_ladipage_ai_content(db: Session, lp: Ladipage) -> List[str]:
    """Sinh toàn bộ section AI + SEO. Trả danh sách lỗi section (rỗng = OK)."""
    errors: List[str] = []
    db.refresh(lp)
    sections = sorted(lp.sections, key=lambda s: s.order_index)
    for section in sections:
        if section.section_type == "products_grid":
            continue
        try:
            new_data = generate_or_regenerate_section(db, lp, section, target="all")
            section.data = new_data
            section.status = "ready"
            section.error_message = None
        except Exception as exc:
            section.status = "error"
            section.error_message = str(exc)[:2000]
            errors.append(f"{section.section_type}: {exc}")
            logger.warning("Ladipage %s section %s bootstrap lỗi: %s", lp.id, section.section_type, exc)
    db.flush()

    try:
        hero = next((s for s in sections if s.section_type == "hero"), None)
        headline = (hero.data or {}).get("headline") if hero and hero.data else None
        subheadline = (hero.data or {}).get("subheadline") if hero and hero.data else None
        generate_and_save_ladipage_seo(
            db,
            lp,
            hero_headline=headline,
            hero_subheadline=subheadline,
            only_missing=False,
        )
    except Exception as exc:
        errors.append(f"seo: {exc}")
        logger.warning("Ladipage %s bootstrap SEO lỗi: %s", lp.id, exc)

    return errors


def publish_ladipage(db: Session, lp: Ladipage) -> None:
    lp.status = "published"
    lp.published_at = datetime.now(timezone.utc)
    db.flush()


def bootstrap_single_product_ladipage(
    db: Session,
    product: Product,
    *,
    created_by: Optional[int] = None,
    publish: bool = False,
    skip_if_exists: bool = True,
) -> Optional[Ladipage]:
    """
    Tạo ladipage 1 SP đầy đủ cho product. Trả None nếu skip (đã có ladipage).
    """
    if skip_if_exists and find_single_product_ladipages_for_product(db, int(product.id)):
        return None

    lp = create_single_product_ladipage_record(db, product, created_by=created_by)
    fill_ladipage_ai_content(db, lp)
    if publish:
        publish_ladipage(db, lp)
    db.commit()
    db.refresh(lp)
    return lp
