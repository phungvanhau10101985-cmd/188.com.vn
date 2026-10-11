"""Kho ảnh size/giặt đã dịch theo shop Trung Quốc + danh mục cấp 2."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from sqlalchemy.exc import IntegrityError

from app.crud.product_category_size_guide import _slug_segments

logger = logging.getLogger(__name__)

_sheet_columns_ready = False
APPAREL_SHEET_RENDER_VERSION = "table-only-1"

_APPAREL_L1 = {
    "do-lot-nam",
    "do-lot-nu",
    "trang-phuc-bau-hau-san",
}
_FASHION_L1 = {
    "thoi-trang-nam",
    "thoi-trang-nu",
    "thoi-trang-tre-em",
}
_EXCLUDED_L1_PREFIXES = (
    "giay-dep",
    "tui-xach",
    "phu-kien",
    "vali",
    "dong-ho",
    "trang-suc",
)
_APPAREL_PARTS = {"ao", "quan", "vay", "dam", "legging", "bra", "bikini", "pijama", "pyjama"}


def normalize_shop_name_chinese(raw: Optional[str]) -> str:
    return " ".join((raw or "").strip().lower().split())[:200]


def category_level2_slug_from_full_slug(full_slug: Optional[str]) -> str:
    _, cat2 = _slug_segments(full_slug)
    return (cat2 or "").strip()[:300]


def explicit_ai_image_requested(product, job_override: Optional[bool]) -> bool:
    """Job bật AI thì mọi ảnh đi GPT. Tắt AI thì không gọi model ảnh."""
    if job_override is False:
        return False
    if job_override is True:
        return True
    info = getattr(product, "product_info", None)
    info = info if isinstance(info, dict) else {}
    loc = info.get("image_localization")
    return isinstance(loc, dict) and loc.get("allow_ai_models") is True


def select_localization_engine(
    *,
    classification: str,
    allows_ai: bool,
    gemini_mode: str = "openai",
    has_size_or_laundry: bool = False,
    force_ai: bool = False,
) -> str:
    from app.services.image_localization_tool.nano_rules import (
        select_localization_engine as _select,
    )

    return _select(
        classification=classification,
        allows_ai=allows_ai,
        gemini_mode=gemini_mode,
        has_size_or_laundry=has_size_or_laundry,
        force_ai=force_ai,
    )


def language_prompt(language: str, remove_model: bool = False, strip_photos: bool = False) -> str:
    from app.services.image_localization_tool.nano_rules import language_prompt as _prompt

    return _prompt(language, remove_model=remove_model, strip_photos=strip_photos)


def _slug_parts(slug: str) -> set:
    return {part for part in (slug or "").strip().lower().replace("_", "-").split("-") if part}


def _excluded_slug(slug: str) -> bool:
    text = (slug or "").strip().lower()
    if not text:
        return False
    if any(text == prefix or text.startswith(prefix + "-") for prefix in _EXCLUDED_L1_PREFIXES):
        return True
    parts = _slug_parts(text)
    if parts & {"giay", "dep", "tui", "balo", "vali", "khan"}:
        return True
    if {"phu", "kien"} <= parts or {"dong", "ho"} <= parts or {"trang", "suc"} <= parts:
        return True
    return "kinh" in parts and "mat" in parts


def _apparel_slug(slug: str) -> bool:
    text = (slug or "").strip().lower()
    if not text or _excluded_slug(text):
        return False
    if text.startswith(("do-lot", "do-ngu", "do-boi", "do-mac-bau", "set-do", "do-bo")) or "trang-phuc" in text:
        return True
    parts = _slug_parts(text)
    if parts & _APPAREL_PARTS:
        return True
    if "chan" in parts and "vay" in parts:
        return True
    return "set" in parts and ("do" in parts or "bo" in parts)


def _apparel_name(name: str) -> bool:
    text = " ".join((name or "").strip().lower().split())
    if not text:
        return False
    if any(word in text for word in ("giày", "giay", "dép", "túi", "balo", "phụ kiện", "phu kien")):
        return False
    return any(
        word in text
        for word in ("áo", "quần", "váy", "đầm", "đồ lót", "đồ ngủ", "legging", "set đồ", "đồ bộ")
    )


def is_apparel_category(full_slug: Optional[str] = None, cat2_name: str = "") -> bool:
    """Quần áo: áo, quần, váy, set, đồ lót, đồ ngủ. Giày, túi, phụ kiện không tính."""
    l1, l2 = _slug_segments(full_slug)
    l1 = (l1 or "").strip().lower()
    l2 = (l2 or "").strip().lower()
    if _excluded_slug(l1) or _excluded_slug(l2):
        return False
    if l1 in _APPAREL_L1:
        return True
    if l1 in _FASHION_L1:
        return _apparel_slug(l2) or _apparel_name(cat2_name)
    if not l1 and (l2 or cat2_name):
        return _apparel_slug(l2) or _apparel_name(cat2_name)
    return False


def product_uses_apparel_size_laundry(db, product) -> bool:
    full_slug = ""
    cat_id = getattr(product, "category_id", None)
    if db is not None and cat_id:
        from app.models.category import Category

        row = db.query(Category.full_slug).filter(Category.id == int(cat_id)).first()
        if row is not None:
            value = getattr(row, "full_slug", None)
            if value is None and not isinstance(row, str):
                try:
                    value = row[0]
                except Exception:
                    value = None
            full_slug = str(value or "")
    name = (getattr(product, "subcategory", None) or "").strip()
    return is_apparel_category(full_slug, cat2_name=name)


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


def _ensure_sheet_kind_columns(db) -> None:
    global _sheet_columns_ready
    if _sheet_columns_ready:
        return
    from sqlalchemy import text

    db.execute(
        text(
            "ALTER TABLE shop_cat2_size_laundry_posters "
            "ADD COLUMN IF NOT EXISTS size_image_url VARCHAR(800)"
        )
    )
    db.execute(
        text(
            "ALTER TABLE shop_cat2_size_laundry_posters "
            "ADD COLUMN IF NOT EXISTS laundry_image_url VARCHAR(800)"
        )
    )
    db.execute(
        text(
            "ALTER TABLE shop_cat2_size_laundry_posters "
            "ADD COLUMN IF NOT EXISTS render_version VARCHAR(40)"
        )
    )
    db.commit()
    _sheet_columns_ready = True


def lookup_stored_sheets(shop_norm: str, cat2_slug: str, *, render_version: Optional[str] = None) -> dict:
    """URL đã lưu theo loại size/laundry. Bản cũ một URL được coi là cả hai loại.

    render_version đặt thì chỉ trả bản đúng phiên. Bản kho cũ không có phiên bị bỏ qua.
    """
    shop = (shop_norm or "").strip()
    slug = (cat2_slug or "").strip()
    if not shop or not slug:
        return {}
    from app.db.session import SessionLocal
    from app.models.shop_size_laundry_poster import ShopCat2SizeLaundryPoster

    db = SessionLocal()
    try:
        _ensure_sheet_kind_columns(db)
        row = (
            db.query(ShopCat2SizeLaundryPoster)
            .filter(
                ShopCat2SizeLaundryPoster.shop_name_chinese_norm == shop,
                ShopCat2SizeLaundryPoster.category_level2_slug == slug,
            )
            .first()
        )
        if row is None:
            return {}
        if render_version is not None:
            got = (getattr(row, "render_version", None) or "").strip()
            if got != render_version:
                return {}
        size_url = (getattr(row, "size_image_url", None) or "").strip()
        laundry_url = (getattr(row, "laundry_image_url", None) or "").strip()
        legacy = (getattr(row, "image_url", None) or "").strip()
        if not size_url and not laundry_url and legacy:
            size_url = laundry_url = legacy
        stored = {}
        if size_url:
            stored["size"] = size_url
        if laundry_url:
            stored["laundry"] = laundry_url
        return stored
    except Exception as exc:
        logger.warning("Đọc kho ảnh size/giặt lỗi: %s", exc)
        return {}
    finally:
        db.close()


def save_sheet_kinds(
    shop_norm: str,
    cat2_slug: str,
    kinds: Sequence[str],
    image_url: str,
    source_product_id: Optional[str] = None,
    render_version: Optional[str] = None,
) -> bool:
    """Ghi URL theo từng loại trên ảnh. Cùng URL cho mọi loại thì lần sau được dùng lại."""
    shop = (shop_norm or "").strip()
    slug = (cat2_slug or "").strip()
    url = (image_url or "").strip()
    kind_list = [kind for kind in kinds if kind in ("size", "laundry")]
    if not shop or not slug or not url or not kind_list:
        return False
    from app.db.session import SessionLocal
    from app.models.shop_size_laundry_poster import ShopCat2SizeLaundryPoster

    db = SessionLocal()
    try:
        _ensure_sheet_kind_columns(db)
        row = (
            db.query(ShopCat2SizeLaundryPoster)
            .filter(
                ShopCat2SizeLaundryPoster.shop_name_chinese_norm == shop,
                ShopCat2SizeLaundryPoster.category_level2_slug == slug,
            )
            .first()
        )
        if row is None:
            row = ShopCat2SizeLaundryPoster(
                shop_name_chinese_norm=shop,
                category_level2_slug=slug,
                image_url=url[:800],
                source_product_id=(source_product_id or None),
            )
            db.add(row)
        existing_version = (getattr(row, "render_version", None) or "").strip()
        if not render_version and existing_version == APPAREL_SHEET_RENDER_VERSION:
            return False
        row.image_url = url[:800]
        if source_product_id:
            row.source_product_id = source_product_id
        if "size" in kind_list:
            row.size_image_url = url[:800]
        if "laundry" in kind_list:
            row.laundry_image_url = url[:800]
        if render_version:
            row.render_version = render_version[:40]
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
