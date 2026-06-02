"""Sản phẩm kho thanh lý duyệt hoàn — id dạng HN256/XL hoặc HN256/Đen/XL."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product

# Cột clone từ SP gốc khi import kho (ngoại trừ id/slug/tồn/biến thể/giá nếu Excel có).
_WAREHOUSE_CLONE_FIELDS = (
    "origin",
    "brand_name",
    "name",
    "description",
    "shop_name",
    "shop_id",
    "pro_lower_price",
    "pro_high_price",
    "group_rating",
    "group_question",
    "images",
    "gallery",
    "link_default",
    "video_link",
    "main_image",
    "likes",
    "purchases",
    "rating_total",
    "question_total",
    "rating_point",
    "deposit_require",
    "category",
    "subcategory",
    "sub_subcategory",
    "raw_category",
    "raw_subcategory",
    "raw_sub_subcategory",
    "material",
    "style",
    "occasion",
    "features",
    "weight",
    "meta_title",
    "meta_description",
    "meta_keywords",
    "product_info",
    "chinese_name",
    "shop_name_chinese",
    "category_id",
)

_SIZE_LIKE_RE = re.compile(
    r"^(?i)(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|\d{1,2}(?:\.\d)?|\d{2,3})$"
)


def parse_warehouse_product_id(product_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    HN256/XL → base HN256, size XL
    HN256/XL/2 → base HN256, size XL, unit 2
    HN256/Đen/XL → base HN256, color Đen, size XL
    """
    raw = str(product_id or "").strip()
    if "/" not in raw:
        return None
    parts = [p.strip() for p in raw.split("/") if p.strip()]
    if len(parts) < 2:
        return None
    base_sku = parts[0]
    if not base_sku:
        return None

    out: Dict[str, Any] = {"base_sku": base_sku, "warehouse_color": None, "warehouse_size": None}
    if len(parts) == 2:
        seg = parts[1]
        if _SIZE_LIKE_RE.match(seg):
            out["warehouse_size"] = seg.upper() if seg.isalpha() else seg
        else:
            out["warehouse_color"] = seg
        return out

    mid, tail = parts[1], parts[2]
    if tail.isdigit() and _SIZE_LIKE_RE.match(mid):
        out["warehouse_size"] = mid.upper() if mid.isalpha() else mid
        out["warehouse_unit"] = tail
        return out
    if _SIZE_LIKE_RE.match(tail):
        out["warehouse_color"] = mid
        out["warehouse_size"] = tail.upper() if tail.isalpha() else tail
        return out
    out["warehouse_color"] = mid
    out["warehouse_size"] = tail
    return out


def is_warehouse_clearance_product_id(product_id: Optional[str]) -> bool:
    return parse_warehouse_product_id(product_id) is not None


def is_source_product_oos(product: Product) -> bool:
    st = (getattr(product, "source_stock_status", None) or "").strip().lower()
    return st == "out_of_stock"


def find_parent_product_by_base_sku(db: Session, base_sku: str) -> Optional[Product]:
    sku = str(base_sku or "").strip()
    if not sku:
        return None
    return (
        db.query(Product)
        .filter(
            Product.is_warehouse_clearance == False,  # noqa: E712
            or_(Product.code == sku, Product.product_id == sku),
        )
        .order_by(Product.id.asc())
        .first()
    )


def list_warehouse_variants_for_base_sku(
    db: Session,
    base_sku: str,
    *,
    active_only: bool = True,
) -> List[Product]:
    sku = str(base_sku or "").strip()
    if not sku:
        return []
    q = db.query(Product).filter(
        Product.is_warehouse_clearance == True,  # noqa: E712
        Product.base_sku == sku,
    )
    if active_only:
        q = q.filter(Product.is_active == True)  # noqa: E712
    return q.order_by(Product.product_id.asc()).all()


def warehouse_variants_in_stock(db: Session, base_sku: str) -> List[Product]:
    return [p for p in list_warehouse_variants_for_base_sku(db, base_sku) if int(p.available or 0) > 0]


def any_warehouse_stock_for_product(db: Session, product: Product) -> bool:
    base = _resolve_base_sku_for_parent(product)
    if not base:
        return False
    return len(warehouse_variants_in_stock(db, base)) > 0


def _resolve_base_sku_for_parent(product: Product) -> Optional[str]:
    if getattr(product, "is_warehouse_clearance", False):
        return (getattr(product, "base_sku", None) or product.code or "").strip() or None
    code = (product.code or "").strip()
    if code:
        return code
    pid = (product.product_id or "").strip()
    if pid and "/" not in pid:
        return pid
    return None


def get_warehouse_clearance_settings(db: Session) -> Tuple[bool, float]:
    from app.models.sale_calendar import SaleCalendarSettings
    from app.services import sale_calendar as sale_calendar_svc

    sale_calendar_svc.ensure_sale_calendar_defaults(db)
    row = db.query(SaleCalendarSettings).filter(SaleCalendarSettings.id == 1).first()
    if not row:
        return False, 0.0
    enabled = bool(getattr(row, "warehouse_clearance_enabled", True))
    pct_raw = getattr(row, "warehouse_clearance_discount_percent", None)
    try:
        pct = float(pct_raw) if pct_raw is not None else 0.0
    except (TypeError, ValueError):
        pct = 0.0
    return enabled, max(0.0, min(100.0, pct))


def apply_clearance_pricing(list_price: float, *, enabled: bool, percent: float) -> Dict[str, Any]:
    base = max(0.0, float(list_price or 0))
    if base <= 0 or not enabled or percent <= 0:
        return {
            "list_price": base,
            "display_price": base,
            "original_price": base,
            "savings_amount": 0.0,
            "clearance_percent": 0.0,
        }
    pct = max(0.0, min(100.0, float(percent)))
    savings = base * pct / 100.0
    display = max(0.0, round(base - savings))
    return {
        "list_price": base,
        "display_price": float(display),
        "original_price": base,
        "savings_amount": float(round(savings)),
        "clearance_percent": pct,
    }


def warehouse_variant_payload(db: Session, wh: Product) -> Dict[str, Any]:
    enabled, pct = get_warehouse_clearance_settings(db)
    base_price = float(wh.price or 0)
    pricing = apply_clearance_pricing(base_price, enabled=enabled, percent=pct)
    wh_color = (wh.color or "").strip()
    if not wh_color and wh.colors:
        try:
            first = wh.colors[0]
            if isinstance(first, dict):
                wh_color = str(first.get("name") or first.get("value") or "").strip()
            elif isinstance(first, str):
                wh_color = first.strip()
        except (IndexError, TypeError, AttributeError):
            pass
    wh_size = ""
    if wh.sizes:
        try:
            wh_size = str(wh.sizes[0] or "").strip()
        except (IndexError, TypeError):
            pass
    return {
        "id": wh.id,
        "product_id": wh.product_id,
        "color": wh_color or None,
        "size": wh_size or None,
        "available": int(wh.available or 0),
        "list_price": pricing["list_price"],
        "display_price": pricing["display_price"],
        "original_price": pricing["original_price"],
        "savings_amount": pricing["savings_amount"],
        "clearance_percent": pricing["clearance_percent"],
        "main_image": wh.main_image,
    }


def enrich_parent_with_warehouse_clearance(db: Session, payload: Dict[str, Any], product: Product) -> None:
    if getattr(product, "is_warehouse_clearance", False):
        return
    base = _resolve_base_sku_for_parent(product)
    source_oos = is_source_product_oos(product)
    payload["source_oos"] = source_oos
    variants: List[Dict[str, Any]] = []
    if base:
        for wh in list_warehouse_variants_for_base_sku(db, base):
            if int(wh.available or 0) <= 0:
                continue
            variants.append(warehouse_variant_payload(db, wh))
    payload["warehouse_variants"] = variants
    enabled, pct = get_warehouse_clearance_settings(db)
    payload["warehouse_clearance"] = {
        "enabled": enabled,
        "discount_percent": pct,
    }


def _apply_warehouse_variant_fields(product_data: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    wh_size = parsed.get("warehouse_size")
    wh_color = parsed.get("warehouse_color")
    if not wh_size and product_data.get("sizes"):
        sizes_raw = product_data.get("sizes")
        if isinstance(sizes_raw, list) and sizes_raw:
            wh_size = str(sizes_raw[0]).strip()
    if not wh_color:
        wh_color = (product_data.get("color") or "").strip() or None

    if wh_size:
        product_data["sizes"] = [str(wh_size)]
    if wh_color:
        product_data["color"] = wh_color
        product_data["colors"] = [{"name": wh_color, "value": wh_color}]

    product_data["is_warehouse_clearance"] = True
    product_data["base_sku"] = parsed["base_sku"]
    if not str(product_data.get("code") or "").strip():
        product_data["code"] = parsed["base_sku"]
    product_data["is_active"] = True
    product_data["source_stock_status"] = "unknown"


def apply_warehouse_import_from_row(product_data: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """Chưa có SP gốc — dùng dữ liệu file import, chỉ gắn metadata kho."""
    _apply_warehouse_variant_fields(product_data, parsed)


def merge_clone_from_parent(parent: Product, product_data: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """Ghi đè product_data bằng dữ liệu SP gốc; giữ size/màu/giá/tồn từ dòng import."""
    keep_price = product_data.get("price")
    keep_available = product_data.get("available")
    keep_name = product_data.get("name")
    for field in _WAREHOUSE_CLONE_FIELDS:
        if hasattr(parent, field):
            product_data[field] = getattr(parent, field)

    _apply_warehouse_variant_fields(product_data, parsed)

    if keep_price is not None and float(keep_price or 0) > 0:
        product_data["price"] = keep_price
    elif parent.price is not None:
        product_data["price"] = parent.price

    if keep_available is not None:
        product_data["available"] = keep_available
    if keep_name and str(keep_name).strip():
        product_data["name"] = keep_name


def enrich_standalone_warehouse_product(db: Session, payload: Dict[str, Any], product: Product) -> None:
    """PDP trực tiếp dòng kho khi chưa có SP gốc cùng base_sku."""
    enabled, pct = get_warehouse_clearance_settings(db)
    base = float(payload.get("price") or 0)
    pricing = apply_clearance_pricing(base, enabled=enabled, percent=pct)
    payload["price"] = pricing["display_price"]
    if pricing["savings_amount"] > 0:
        payload["original_price"] = base
    payload["site_sale"] = None
    payload["source_oos"] = False
    payload["warehouse_variants"] = []
    payload["warehouse_clearance"] = {
        "enabled": enabled,
        "discount_percent": pct,
    }


def assert_product_deletion_allowed(db: Session, product: Product) -> None:
    """Raise ValueError với message tiếng Việt nếu không được xóa."""
    if getattr(product, "is_warehouse_clearance", False):
        if int(product.available or 0) > 0:
            raise ValueError(
                f"Sản phẩm kho «{product.product_id}» còn tồn ({product.available}) — "
                "hạ tồn về 0 trước khi xóa."
            )
        return

    base = _resolve_base_sku_for_parent(product)
    if not base:
        return

    in_stock = warehouse_variants_in_stock(db, base)
    if in_stock:
        ids = ", ".join(p.product_id for p in in_stock[:5])
        extra = f" (+{len(in_stock) - 5} dòng)" if len(in_stock) > 5 else ""
        raise ValueError(
            f"Không thể xóa «{product.product_id}»: còn {len(in_stock)} dòng kho thanh lý có tồn "
            f"({ids}{extra}). Chỉ xóa khi hết tồn kho."
        )

    if is_source_product_oos(product):
        # Nguồn OOS nhưng kho đã hết — cho phép xóa
        return

    # Còn hàng nguồn: vẫn cho xóa admin thủ công (không chặn) — chỉ chặn khi còn kho


def parent_has_deletion_block(db: Session, product: Product) -> Optional[str]:
    try:
        assert_product_deletion_allowed(db, product)
        return None
    except ValueError as exc:
        return str(exc)
