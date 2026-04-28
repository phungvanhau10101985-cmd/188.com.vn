"""
Feed TSV cho Meta Commerce Manager (Facebook/Instagram) và TikTok Catalog (Ads / Shop).
Định dạng gần với Google Product Specification; Meta/TikTok chấp nhận TSV/CSV qua URL.

- Meta: https://www.facebook.com/business/help/120325381656392
- TikTok: https://ads.tiktok.com/help/article/catalog-product-parameters

Cột bắt buộc / khuyến nghị: điền từ Product; danh mục Meta (`fb_product_category`) và taxonomy Google
(`google_product_category`) nên chỉnh qua biến môi trường nếu cần chính xác từng ngành hàng.
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.merchant_feed_tsv import (
    _pick_additional_images,
    _pick_main_image,
    _price_gmc,
    _product_canonical_link,
    _product_type_breadcrumb,
    _sizes_string,
    _strip_html,
    _tsv_cell,
    _weight_value,
)


def _availability_human(product: Product) -> str:
    """Meta và TikTok: thường dùng 'in stock' / 'out of stock' có khoảng trắng."""
    av = getattr(product, "available", None)
    try:
        n = int(av) if av is not None else 0
    except (TypeError, ValueError):
        n = 0
    return "in stock" if n > 0 else "out of stock"


# Meta Commerce — tên cột theo tài liệu Catalog (US English)
META_TSV_COLUMNS = (
    "id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
    "additional_image_link",
    "google_product_category",
    "fb_product_category",
    "product_type",
    "color",
    "size",
    "sale_price",
    "sale_price_effective_date",
    "item_group_id",
    "gender",
    "age_group",
)

# TikTok — sku_id là ID nội dung; các trường còn lại align Google-style catalog
TIKTOK_TSV_COLUMNS = (
    "sku_id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
    "google_product_category",
    "additional_image_link",
    "product_type",
    "color",
    "size",
    "sale_price",
    "sale_price_effective_date",
    "item_group_id",
    "gender",
    "age_group",
    "shipping_weight",
    "video_link",
)


def _google_category(default: str, product: Product) -> str:
    if default:
        return _tsv_cell(default)
    return _tsv_cell(_product_type_breadcrumb(product))


def meta_row_values(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    fb_product_category: str,
    google_product_category_default: str,
) -> list[str]:
    title = _tsv_cell(getattr(product, "name", "") or "")
    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"
    link = _product_canonical_link(product, shop_base_url)
    price = _price_gmc(getattr(product, "price", None), currency)
    gcat = _google_category(google_product_category_default, product)
    fb = _tsv_cell(fb_product_category) or gcat

    return [
        _tsv_cell(getattr(product, "product_id", "") or ""),
        title,
        _strip_html(getattr(product, "description", None)),
        _availability_human(product),
        "new",
        price,
        link,
        _pick_main_image(product, image_site_base),
        brand,
        _pick_additional_images(product, image_site_base),
        gcat,
        fb,
        _tsv_cell(_product_type_breadcrumb(product)),
        _tsv_cell(getattr(product, "color", None)),
        _sizes_string(product),
        "",
        "",
        "",
        "",
        "",
    ]


def tiktok_row_values(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    google_product_category_default: str,
) -> list[str]:
    title = _tsv_cell(getattr(product, "name", "") or "")
    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"
    link = _product_canonical_link(product, shop_base_url)
    price = _price_gmc(getattr(product, "price", None), currency)
    gcat = _google_category(google_product_category_default, product)
    vid = _tsv_cell(getattr(product, "video_link", None))

    return [
        _tsv_cell(getattr(product, "product_id", "") or ""),
        title,
        _strip_html(getattr(product, "description", None)),
        _availability_human(product),
        "new",
        price,
        link,
        _pick_main_image(product, image_site_base),
        brand,
        gcat,
        _pick_additional_images(product, image_site_base),
        _tsv_cell(_product_type_breadcrumb(product)),
        _tsv_cell(getattr(product, "color", None)),
        _sizes_string(product),
        "",
        "",
        "",
        "",
        "",
        _weight_value(product),
        vid,
    ]


def iter_meta_catalog_lines(
    db: Session,
    shop_base_url: str,
    *,
    currency: str,
    image_site_base: str | None,
    fb_product_category: str,
    google_product_category_default: str,
    only_active: bool = True,
    yield_per: int = 1000,
) -> Iterator[str]:
    img_base = (image_site_base or shop_base_url).rstrip("/")
    yield "\t".join(META_TSV_COLUMNS)
    q = db.query(Product).order_by(Product.id)
    if only_active:
        q = q.filter(Product.is_active.is_(True))
    for p in q.yield_per(max(50, yield_per)):
        vals = meta_row_values(
            p,
            shop_base_url,
            img_base,
            currency,
            fb_product_category=fb_product_category,
            google_product_category_default=google_product_category_default,
        )
        yield "\t".join(vals)


def iter_tiktok_catalog_lines(
    db: Session,
    shop_base_url: str,
    *,
    currency: str,
    image_site_base: str | None,
    google_product_category_default: str,
    only_active: bool = True,
    yield_per: int = 1000,
) -> Iterator[str]:
    img_base = (image_site_base or shop_base_url).rstrip("/")
    yield "\t".join(TIKTOK_TSV_COLUMNS)
    q = db.query(Product).order_by(Product.id)
    if only_active:
        q = q.filter(Product.is_active.is_(True))
    for p in q.yield_per(max(50, yield_per)):
        vals = tiktok_row_values(
            p,
            shop_base_url,
            img_base,
            currency,
            google_product_category_default=google_product_category_default,
        )
        yield "\t".join(vals)
