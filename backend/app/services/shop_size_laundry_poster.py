"""Kho ảnh size/giặt đã dịch theo shop Trung Quốc + danh mục cấp 2."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.crud.product_category_size_guide import _slug_segments

logger = logging.getLogger(__name__)

_LANGUAGE_LABELS = {
    "vi": "Vietnamese",
    "en": "English",
    "th": "Thai",
    "id": "Indonesian",
}


def normalize_shop_name_chinese(raw: Optional[str]) -> str:
    return " ".join((raw or "").strip().lower().split())[:200]


def category_level2_slug_from_full_slug(full_slug: Optional[str]) -> str:
    _, cat2 = _slug_segments(full_slug)
    return (cat2 or "").strip()[:300]


def explicit_ai_image_requested(product, job_override: Optional[bool]) -> bool:
    """Ảnh thường chỉ lên Gemini khi job hoặc sản phẩm được chỉ định AI."""
    if job_override is False:
        return False
    if job_override is True:
        return True
    info = getattr(product, "product_info", None)
    info = info if isinstance(info, dict) else {}
    loc = info.get("image_localization")
    return isinstance(loc, dict) and loc.get("allow_ai_models") is True


def localization_image_branch(
    *,
    is_size_or_laundry: bool,
    has_chinese: bool,
    size_laundry_ai_enabled: bool,
    explicit_other_ai: bool,
    classifier_type: str,
) -> str:
    """
    delete | keep | gpt | local | explicit_gemini

    Ảnh size/giặt: GPT Image khi job không cấm AI. Ảnh khác: local, trừ khi được chỉ định AI
    và classifier yêu cầu Gemini/GPT.
    """
    if classifier_type == "delete":
        return "delete"
    if is_size_or_laundry:
        if not has_chinese:
            return "keep"
        if size_laundry_ai_enabled:
            return "gpt"
        return "local"
    if classifier_type == "keep":
        return "keep"
    if explicit_other_ai and classifier_type == "gemini":
        return "explicit_gemini"
    return "local"


def size_laundry_nano_prompt(language: str) -> str:
    target = _LANGUAGE_LABELS.get((language or "vi").strip().lower(), language or "Vietnamese")
    return f"""ROLE: E-commerce size-chart and care-label localization agent.

This image is a size chart (how to choose a size) and/or a washing and care instruction sheet.
Translate every Chinese text element into {target}.
Keep height and garment measurements in cm or mm, size labels, the table grid, care icons, colors, and layout unchanged. Do not invent or drop those measurements.
Chinese weight uses 斤, and 1斤 = 0.5kg. Convert every 斤 value to kg by dividing by 2. A bare number in a 体重 or 重量 column with no unit is also 斤: convert it the same way and write kg. Example: 94 under 体重 becomes 47kg, 98 becomes 49kg. Leave values that already say kg, 公斤, or 千克 unchanged, including 47kg.
If a fashion model or a person's face or body appears beside the size chart, remove the entire person and fill that area with the chart background. Keep the size table and care instructions.
Remove website URLs and domains.
Return only the processed image file, with no explanation."""


def collapse_repeated_poster_urls(urls: Sequence[Optional[str]], poster_urls: set) -> List[str]:
    """Giữ một lần mỗi URL ảnh kho trong cùng một danh sách ảnh."""
    seen = set()
    out: List[str] = []
    posters = {u for u in poster_urls if u}
    for url in urls:
        if not url:
            continue
        if url in posters:
            if url in seen:
                continue
            seen.add(url)
        out.append(url)
    return out


def resolve_poster_key(db, product) -> tuple:
    """(shop_name_chinese đã chuẩn hóa, slug danh mục cấp 2). Rỗng nếu thiếu."""
    shop = normalize_shop_name_chinese(getattr(product, "shop_name_chinese", None))
    slug = ""
    cat_id = getattr(product, "category_id", None)
    if db is not None and cat_id:
        from app.models.category import Category

        row = db.query(Category.full_slug).filter(Category.id == int(cat_id)).first()
        if row is not None:
            full_slug = getattr(row, "full_slug", None)
            if full_slug is None and not isinstance(row, str):
                try:
                    full_slug = row[0]
                except Exception:
                    full_slug = None
            slug = category_level2_slug_from_full_slug(full_slug)
    if not slug and db is not None:
        name = (getattr(product, "subcategory", None) or "").strip()
        if name:
            from app.models.category import Category

            row = (
                db.query(Category.slug)
                .filter(Category.level == 2, Category.name == name)
                .first()
            )
            if row is not None:
                slug = (getattr(row, "slug", None) or "")
                if not slug:
                    try:
                        slug = row[0] or ""
                    except Exception:
                        slug = ""
                slug = str(slug).strip()[:300]
    return shop, slug


def lookup_poster_image_url(shop_norm: str, cat2_slug: str) -> Optional[str]:
    shop = (shop_norm or "").strip()
    slug = (cat2_slug or "").strip()
    if not shop or not slug:
        return None
    from app.db.session import SessionLocal
    from app.models.shop_size_laundry_poster import ShopCat2SizeLaundryPoster

    db = SessionLocal()
    try:
        row = (
            db.query(ShopCat2SizeLaundryPoster.image_url)
            .filter(
                ShopCat2SizeLaundryPoster.shop_name_chinese_norm == shop,
                ShopCat2SizeLaundryPoster.category_level2_slug == slug,
            )
            .first()
        )
        if row is None:
            return None
        url = getattr(row, "image_url", None)
        if not url:
            try:
                url = row[0]
            except Exception:
                url = None
        url = (url or "").strip()
        return url or None
    except Exception as exc:
        logger.warning("Đọc kho ảnh size/giặt lỗi: %s", exc)
        return None
    finally:
        db.close()


def save_poster_if_absent(
    shop_norm: str,
    cat2_slug: str,
    image_url: str,
    source_product_id: Optional[str] = None,
) -> bool:
    """Lưu ảnh poster đã dịch. Không ghi đè bản đã có. Trả True khi vừa tạo mới."""
    shop = (shop_norm or "").strip()
    slug = (cat2_slug or "").strip()
    url = (image_url or "").strip()
    if not shop or not slug or not url:
        return False
    from app.db.session import SessionLocal
    from app.models.shop_size_laundry_poster import ShopCat2SizeLaundryPoster

    db = SessionLocal()
    try:
        exists = (
            db.query(ShopCat2SizeLaundryPoster.id)
            .filter(
                ShopCat2SizeLaundryPoster.shop_name_chinese_norm == shop,
                ShopCat2SizeLaundryPoster.category_level2_slug == slug,
            )
            .first()
        )
        if exists:
            return False
        db.add(
            ShopCat2SizeLaundryPoster(
                shop_name_chinese_norm=shop,
                category_level2_slug=slug,
                image_url=url[:800],
                source_product_id=(source_product_id or None),
            )
        )
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
    except Exception as exc:
        db.rollback()
        logger.warning("Lưu kho ảnh size/giặt lỗi: %s", exc)
        return False
    finally:
        db.close()
