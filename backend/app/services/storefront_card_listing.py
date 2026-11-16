"""Listing danh mục storefront: chỉ cột và field mà thẻ sản phẩm đang vẽ.

Không đụng trang chủ, tìm kiếm, admin, PDP. Bỏ mô tả, gallery, giá nhập,
meta SEO và log kho khỏi SELECT lẫn JSON trả về.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import lazyload, load_only

from app.models.product import Product

# Cột nhỏ đủ cho thẻ: ảnh bìa + 2 ảnh dự phòng, giá biến thể, tồn, sale, thanh lý.
STOREFRONT_CARD_COLUMNS = (
    Product.id,
    Product.product_id,
    Product.code,
    Product.name,
    Product.slug,
    Product.price,
    Product.brand_name,
    Product.main_image,
    Product.images,
    Product.video_link,
    Product.available,
    Product.sizes,
    Product.colors,
    Product.color,
    Product.product_info,
    Product.category,
    Product.subcategory,
    Product.sub_subcategory,
    Product.category_id,
    Product.is_active,
    Product.is_warehouse_clearance,
    Product.base_sku,
    Product.deposit_require,
    Product.purchases,
    Product.rating_point,
    Product.rating_total,
    Product.source_stock_status,
)

_CARD_IMAGE_LIMIT = 2


def card_listing_query_options():
    """load_only + không join category. Tránh SELECT description/gallery/consult."""
    return (
        load_only(*STOREFRONT_CARD_COLUMNS),
        lazyload(Product.category_rel),
    )


def is_storefront_category_card_request(
    *,
    admin_list: bool,
    q: Optional[str],
    product_id: Optional[str],
    warehouse_clearance_only: bool,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
) -> bool:
    """Chỉ lưới /danh-muc. Tìm kiếm, admin, kho-sale và trang chủ giữ payload đầy đủ."""
    if admin_list or warehouse_clearance_only:
        return False
    if (q or "").strip() or (product_id or "").strip():
        return False
    return any(str(part or "").strip() for part in (category, subcategory, sub_subcategory))


def _image_urls(value: Any, limit: int = _CARD_IMAGE_LIMIT) -> list:
    if not isinstance(value, list):
        return []
    out: list = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def slim_product_info_for_card(info: Any) -> Optional[dict]:
    """Giữ cặp giá biến thể cho chữ «từ». Bỏ specifications và mô tả trong JSON."""
    if not isinstance(info, dict):
        return None
    variants = info.get("variants")
    if not isinstance(variants, dict):
        return None
    slim: dict = {}
    for key in ("pairs", "price_pairs"):
        rows = variants.get(key)
        if isinstance(rows, list) and rows:
            slim[key] = rows
    if not slim:
        return None
    return {"variants": slim}


def build_storefront_card_payload(product: Any) -> dict:
    images = _image_urls(getattr(product, "images", None))
    return {
        "id": getattr(product, "id", None),
        "product_id": getattr(product, "product_id", None),
        "code": getattr(product, "code", None),
        "name": getattr(product, "name", None),
        "slug": getattr(product, "slug", None),
        "price": getattr(product, "price", None),
        "brand_name": getattr(product, "brand_name", None),
        "main_image": getattr(product, "main_image", None),
        "images": images,
        "video_link": getattr(product, "video_link", None),
        "available": getattr(product, "available", None),
        "sizes": getattr(product, "sizes", None),
        "colors": getattr(product, "colors", None),
        "color": getattr(product, "color", None),
        "product_info": slim_product_info_for_card(getattr(product, "product_info", None)),
        "category": getattr(product, "category", None),
        "subcategory": getattr(product, "subcategory", None),
        "sub_subcategory": getattr(product, "sub_subcategory", None),
        "category_id": getattr(product, "category_id", None),
        "is_active": getattr(product, "is_active", None),
        "is_warehouse_clearance": bool(getattr(product, "is_warehouse_clearance", False)),
        "base_sku": getattr(product, "base_sku", None),
        "deposit_require": getattr(product, "deposit_require", None),
        "purchases": getattr(product, "purchases", None),
        "rating_point": getattr(product, "rating_point", None),
        "rating_total": getattr(product, "rating_total", None),
        "source_stock_status": getattr(product, "source_stock_status", None),
    }
