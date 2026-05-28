"""
Feed TSV cho Meta Commerce Manager (Facebook/Instagram) và TikTok Catalog (Ads / Shop).
Định dạng gần Google Product Specification; Meta/TikTok chấp nhận TSV/CSV qua URL.

- Meta: https://www.facebook.com/business/help/120325381656392
- TikTok: https://ads.tiktok.com/help/article/catalog-product-parameters

Cột `sale_price` / `sale_price_effective_date` luôn có (để trống khi chưa sale); giá trị cùng logic
`merchant_feed_tsv` (`CATALOG_SALE_*` hoặc nguồn ghép sau).

Các trường khác (gender, age_group, item group, custom labels, video): đồng bộ `merchant_feed_tsv` + `product_info` (AK).
Meta dùng `video_url` (link video).

- Danh mục Meta (`fb_product_category`) và fallback Google (`CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY`).
"""
from __future__ import annotations

from typing import Iterator, Optional

from sqlalchemy.orm import Session

from app.models.product import Product
from app.services.merchant_feed_tsv import (
    _custom_label_0_value,
    _custom_labels_1_to_4,
    _item_group_id_value,
    _normalized_age_group,
    _normalized_gender,
    _pick_additional_images,
    _pick_main_image,
    _price_gmc,
    _product_canonical_link,
    _product_type_breadcrumb,
    _sale_price_and_effective,
    _sizes_string,
    _strip_html,
    _tsv_cell,
    _video_feed_url,
    _weight_value,
    resolved_google_product_category,
)


def _availability_human(product: Product) -> str:
    """Meta và TikTok: 'in stock' / 'out of stock'."""
    av = getattr(product, "available", None)
    try:
        n = int(av) if av is not None else 0
    except (TypeError, ValueError):
        n = 0
    return "in stock" if n > 0 else "out of stock"


# --- Meta / TikTok: sale_price & sale_price_effective_date luôn có trong header (ô trống khi chưa KM) ---
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
    "custom_label_0",
    "custom_label_1",
    "custom_label_2",
    "custom_label_3",
    "custom_label_4",
    "video_url",
    "shipping_weight",
)

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


def meta_row_values(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    fb_product_category: str,
    google_product_category_default: str,
    sale_state=None,
    db: Optional[Session] = None,
) -> list[str]:
    from app.services import sale_calendar as sale_calendar_svc

    if sale_state is None and db is not None:
        sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)
    raw_title = getattr(product, "name", "") or ""
    title = _tsv_cell(
        sale_calendar_svc.feed_title_with_sale_prefix(raw_title, sale_state) if sale_state else raw_title
    )
    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"
    link = _product_canonical_link(product, shop_base_url)
    price = _price_gmc(getattr(product, "price", None), currency)
    gcat = resolved_google_product_category(product, google_product_category_default)
    fb = _tsv_cell(fb_product_category) or gcat
    sale_price, sale_eff = _sale_price_and_effective(product, currency, sale_state=sale_state, db=db)
    c0 = _custom_label_0_value(product)
    if sale_state is not None:
        sale_label = sale_calendar_svc.feed_custom_label_for_teaser(sale_state)
        if sale_label:
            c0 = _tsv_cell(sale_label)
    c1, c2, c3, c4 = _custom_labels_1_to_4(product)

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
        sale_price,
        sale_eff,
        _item_group_id_value(product),
        _normalized_gender(product),
        _normalized_age_group(product),
        c0,
        c1,
        c2,
        c3,
        c4,
        _video_feed_url(product),
        _weight_value(product),
    ]


def tiktok_row_values(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    google_product_category_default: str,
    sale_state=None,
    db: Optional[Session] = None,
) -> list[str]:
    from app.services import sale_calendar as sale_calendar_svc

    if sale_state is None and db is not None:
        sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)
    raw_title = getattr(product, "name", "") or ""
    title = _tsv_cell(
        sale_calendar_svc.feed_title_with_sale_prefix(raw_title, sale_state) if sale_state else raw_title
    )
    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"
    link = _product_canonical_link(product, shop_base_url)
    price = _price_gmc(getattr(product, "price", None), currency)
    gcat = resolved_google_product_category(product, google_product_category_default)
    sale_price, sale_eff = _sale_price_and_effective(product, currency, sale_state=sale_state, db=db)

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
        sale_price,
        sale_eff,
        _item_group_id_value(product),
        _normalized_gender(product),
        _normalized_age_group(product),
        _weight_value(product),
        _video_feed_url(product),
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
    from app.services import sale_calendar as sale_calendar_svc

    img_base = (image_site_base or shop_base_url).rstrip("/")
    sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)
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
            sale_state=sale_state,
            db=db,
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
    from app.services import sale_calendar as sale_calendar_svc

    img_base = (image_site_base or shop_base_url).rstrip("/")
    sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)
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
            sale_state=sale_state,
            db=db,
        )
        yield "\t".join(vals)
