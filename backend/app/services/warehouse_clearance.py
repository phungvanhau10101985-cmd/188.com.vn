"""Sản phẩm kho thanh lý duyệt hoàn — id dạng HN256/XL hoặc HN256/Đen/XL."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product

# Listing nhóm / redirect OOS cho dòng kho thanh lý (Sale Sốc, …).
WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH = "/kho-sale"

# Từ khóa tìm «sale» / thanh lý → listing kho (không ?q=sale trên trang chủ).
_SALE_LISTING_SEARCH_SLUGS = frozenset(
    {
        "sale",
        "kho-sale",
        "thanh-ly",
        "thanh-ly-kho",
        "sale-soc",
        "sale-so",
        "hang-sale",
        "hang-thanh-ly",
    }
)


def _sale_search_term_slug(raw: str) -> str:
    """Slug khớp frontend `generateSlug` — dùng nhận diện từ khóa kho sale."""
    import unicodedata

    s = unicodedata.normalize("NFD", str(raw or "").strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 -]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return re.sub(r"-+", "-", s)


def is_sale_listing_search_query(raw_query: Optional[str]) -> bool:
    """True khi người dùng tìm kho sale / thanh lý (một cụm, không phải «áo sale»)."""
    raw = str(raw_query or "").strip()
    if not raw:
        return False
    slug = _sale_search_term_slug(raw)
    if not slug:
        return False
    if slug in _SALE_LISTING_SEARCH_SLUGS:
        return True
    compact = re.sub(r"[^a-z0-9]+", "", slug)
    return compact in {"sale", "khosale", "thanhkho", "salesoc"}

# Cột clone từ SP gốc khi import kho (ảnh/size/màu/tồn/giá lấy từ Excel hoặc rule riêng).
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
    "link_default",
    "video_link",
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
    r"^(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|\d{1,2}(?:\.\d)?|\d{2,3})$",
    re.IGNORECASE,
)
_LISTING_SOURCE_BASE_RE = re.compile(r"^([AT])(\d{6,})$", re.IGNORECASE)


def is_listing_source_base_sku(base_sku: Optional[str]) -> bool:
    """Mã gốc nguồn 1688/Tmall: A932203996836 / T932203996836."""
    return bool(_LISTING_SOURCE_BASE_RE.match(str(base_sku or "").strip()))


def warehouse_safe_slug_token(product_id: Optional[str]) -> str:
    """Mã SP kho dạng H0723/40/3 → h0723-40-3 (an toàn cho URL /products/[slug])."""
    raw = str(product_id or "").strip().lower()
    if not raw:
        return ""
    return re.sub(r"-+", "-", re.sub(r"[/\\]+", "-", raw)).strip("-")


def _parse_listing_source_product_segments(parts: List[str]) -> Dict[str, Any]:
    """
    Mã nguồn 1688/Tmall (A/T + id):
    - A757876600366/4 → ô ảnh màu #4 (không phải size)
    - A757876600366/45/4 → size 45, ô ảnh màu #4
    - A652267320844/XL/3 → size XL, unit 3 (kho thanh lý)
    - A941905898454/40/1 → size 40, unit 1
    """
    base_sku = parts[0]
    out: Dict[str, Any] = {
        "base_sku": base_sku,
        "warehouse_color": None,
        "warehouse_size": None,
        "warehouse_unit": None,
        "listing_color_image_index": None,
    }
    if len(parts) == 2:
        seg = parts[1]
        if seg.isdigit():
            out["listing_color_image_index"] = int(seg)
        else:
            out["warehouse_color"] = seg
        return out

    if len(parts) == 3:
        mid, tail = parts[1], parts[2]
        if _SIZE_LIKE_RE.match(mid) and mid.isalpha():
            out["warehouse_size"] = mid.upper()
            if tail.isdigit():
                out["warehouse_unit"] = tail
            return out
        if _SIZE_LIKE_RE.match(mid) and tail.isdigit():
            out["warehouse_size"] = mid.upper() if mid.isalpha() else mid
            if int(tail) == 1:
                out["warehouse_unit"] = tail
            else:
                out["listing_color_image_index"] = int(tail)
            return out
        if _SIZE_LIKE_RE.match(tail):
            out["warehouse_color"] = mid
            out["warehouse_size"] = tail.upper() if tail.isalpha() else tail
            return out
        out["warehouse_color"] = mid
        out["warehouse_size"] = tail
        return out

    out["warehouse_color"] = parts[1]
    out["warehouse_size"] = parts[-1]
    return out


def _parse_legacy_warehouse_product_segments(parts: List[str]) -> Dict[str, Any]:
    """HN256/XL, HN256/XL/2, HN256/Đen/XL — không áp dụng quy tắc ô ảnh màu 1688."""
    base_sku = parts[0]
    out: Dict[str, Any] = {
        "base_sku": base_sku,
        "warehouse_color": None,
        "warehouse_size": None,
        "warehouse_unit": None,
        "listing_color_image_index": None,
    }
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


def parse_warehouse_product_id(product_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    HN256/XL → base HN256, size XL
    HN256/XL/2 → base HN256, size XL, unit 2
    HN256/Đen/XL → base HN256, color Đen, size XL
    A757876600366/4 → ô ảnh màu 1688 #4 (không phải size 4)
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

    if is_listing_source_base_sku(base_sku):
        return _parse_listing_source_product_segments(parts)
    return _parse_legacy_warehouse_product_segments(parts)


def apply_catalog_visibility_filter(
    query,
    *,
    include_warehouse_products: bool = False,
    warehouse_clearance_only: bool = False,
    has_text_search: bool = False,
):
    """
    Storefront: mặc định ẩn dòng kho thanh lý khỏi danh mục/listing không tìm.
    - warehouse_clearance_only: chỉ SP is_warehouse_clearance (trang /kho-sale).
    - has_text_search: tìm theo q — gồm cả SP thường và kho thanh lý.
    - include_warehouse_products: admin — không lọc.
    """
    if include_warehouse_products:
        return query
    if warehouse_clearance_only:
        return query.filter(Product.is_warehouse_clearance == True)  # noqa: E712
    if has_text_search:
        return query
    return query.filter(
        or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None))  # noqa: E712
    )


def is_warehouse_clearance_product_id(product_id: Optional[str]) -> bool:
    return parse_warehouse_product_id(product_id) is not None


def is_warehouse_cart_product(
    product: Optional[Product],
    product_data: Any = None,
) -> bool:
    """Nhận dòng giỏ kho thanh lý — cờ DB hoặc mã dạng H0723/40/3."""
    if product is not None and getattr(product, "is_warehouse_clearance", False):
        return True
    if product is not None and is_warehouse_clearance_product_id(getattr(product, "product_id", None)):
        return True
    pd = product_data if isinstance(product_data, dict) else {}
    if pd.get("is_warehouse_clearance"):
        return True
    code = str(pd.get("product_id") or "").strip()
    if code and is_warehouse_clearance_product_id(code):
        return True
    return False


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


def parent_pdp_slug_for_warehouse_product(db: Session, product: Product) -> Optional[str]:
    """Slug PDP của SP gốc — không dùng slug dòng kho (thường có suffix product_id)."""
    parsed = parse_warehouse_product_id(getattr(product, "product_id", None))
    if not parsed:
        return None
    parent = find_parent_product_by_base_sku(db, parsed["base_sku"])
    if parent is None:
        return None
    slug = (parent.slug or "").strip()
    return slug or None


def apply_warehouse_cart_product_data_slug(
    db: Session,
    product: Product,
    product_data: Dict[str, Any],
) -> None:
    """Ghi slug PDP gốc vào product_data dòng kho (in-place)."""
    parent_slug = parent_pdp_slug_for_warehouse_product(db, product)
    if parent_slug:
        product_data["slug"] = parent_slug
        product_data["parent_slug"] = parent_slug


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
        or_(
            Product.base_sku == sku,
            Product.product_id.like(f"{sku}/%"),
        ),
    )
    if active_only:
        q = q.filter(Product.is_active == True)  # noqa: E712
    return q.order_by(Product.product_id.asc()).all()


def warehouse_variants_in_stock(db: Session, base_sku: str) -> List[Product]:
    from app.services.warehouse_stock import warehouse_sellable_qty

    return [
        p
        for p in list_warehouse_variants_for_base_sku(db, base_sku)
        if warehouse_sellable_qty(p) > 0
    ]


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
        try:
            from app.crud.product import _listing_source_prefix_from_product_id

            src = _listing_source_prefix_from_product_id(pid)
            if src and src.get("prefix"):
                return str(src["prefix"]).strip()
        except Exception:
            pass
        return pid
    return None


def _warehouse_row_base_sku(wh: Product) -> str:
    base = (getattr(wh, "base_sku", None) or "").strip()
    if base:
        return base
    parsed = parse_warehouse_product_id(getattr(wh, "product_id", None))
    if parsed:
        return str(parsed.get("base_sku") or "").strip()
    return (getattr(wh, "code", None) or "").strip()


def find_parent_for_warehouse_row(db: Session, wh: Product) -> Optional[Product]:
    """SP gốc (không phải dòng kho) — dùng đồng bộ giá list thanh lý."""
    base = _warehouse_row_base_sku(wh)
    if base:
        parent = find_parent_product_by_base_sku(db, base)
        if parent is not None:
            return parent
        try:
            from app.services.return_warehouse_intake import find_listing_parent_product

            listing_parent = find_listing_parent_product(db, base)
            if listing_parent is not None:
                return listing_parent
        except Exception:
            pass
    pi = getattr(wh, "product_info", None)
    if isinstance(pi, dict):
        pid = str(pi.get("parent_product_id") or "").strip()
        if pid:
            row = db.query(Product).filter(Product.product_id == pid).first()
            if row is not None and not getattr(row, "is_warehouse_clearance", False):
                return row
    return None


def resolve_warehouse_list_price(db: Session, wh: Product) -> float:
    """
    Giá gốc (list) để tính % thanh lý kho — ưu tiên SP gốc trên shop, không dùng giá cũ trên dòng kho.
    """
    parent = find_parent_for_warehouse_row(db, wh)
    if parent is not None and parent.price is not None:
        try:
            p = float(parent.price)
            if p > 0:
                return p
        except (TypeError, ValueError):
            pass
    try:
        return max(0.0, float(wh.price or 0))
    except (TypeError, ValueError):
        return 0.0


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


def resolve_checkout_line_prices(
    db: Session,
    product: Product,
    *,
    user=None,
) -> Tuple[float, float]:
    """
    (unit_price, list_price) cho checkout/đặt hàng — đồng bộ với giỏ hàng.
    Dòng kho thanh lý: áp % giảm admin trên giá list SP gốc (resolve_warehouse_list_price).
    Hàng thường: site sale active (effective_unit_price).
    """
    from app.services.sale_calendar import effective_unit_price

    if is_warehouse_cart_product(product):
        list_price = resolve_warehouse_list_price(db, product)
        _enabled, pct = get_warehouse_clearance_settings(db)
        pricing = apply_clearance_pricing(list_price, percent=pct)
        return float(pricing["display_price"]), float(pricing["list_price"])
    list_price = float(product.price or 0)
    unit = float(effective_unit_price(db, list_price, user=user))
    return unit, list_price


def apply_clearance_pricing(list_price: float, *, percent: float) -> Dict[str, Any]:
    """
    Áp dụng % giảm kho thanh lý (mức cấu hình admin).
    `warehouse_clearance_enabled` chỉ điều khiển hiển thị block kho trên SP gốc — không chặn giá sale.
    """
    base = max(0.0, float(list_price or 0))
    if base <= 0 or percent <= 0:
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
    from app.services.warehouse_stock import warehouse_sellable_qty

    enabled, pct = get_warehouse_clearance_settings(db)
    base_price = resolve_warehouse_list_price(db, wh)
    pricing = apply_clearance_pricing(base_price, percent=pct)
    sellable = warehouse_sellable_qty(wh)
    wh_color = (wh.color or "").strip()
    wh_color_img: Optional[str] = None
    if wh.colors:
        try:
            first = wh.colors[0]
            if isinstance(first, dict):
                if not wh_color:
                    wh_color = str(first.get("name") or first.get("value") or "").strip()
                wh_color_img = (
                    str(first.get("img") or first.get("image") or first.get("image_url") or "")
                    .strip()
                    or None
                )
            elif isinstance(first, str):
                if not wh_color:
                    wh_color = first.strip()
        except (IndexError, TypeError, AttributeError):
            pass
    wh_size = ""
    if wh.sizes:
        try:
            wh_size = str(wh.sizes[0] or "").strip()
        except (IndexError, TypeError):
            pass
    main_img = (str(wh.main_image or "").strip() or None) or wh_color_img
    return {
        "id": wh.id,
        "product_id": wh.product_id,
        "color": wh_color or None,
        "size": wh_size or None,
        "available": sellable,
        "warehouse_available": int(wh.available or 0),
        "list_price": pricing["list_price"],
        "display_price": pricing["display_price"],
        "original_price": pricing["original_price"],
        "savings_amount": pricing["savings_amount"],
        "clearance_percent": pricing["clearance_percent"],
        "main_image": main_img,
        "color_image": wh_color_img or main_img,
    }


def enrich_snapshot_product_data_for_card(
    db: Session,
    product_id: int,
    product_data: Any,
) -> Dict[str, Any]:
    """Bổ sung warehouse_variants / Màu·Size cho snapshot (đã xem, yêu thích, …)."""
    base: Dict[str, Any] = dict(product_data) if isinstance(product_data, dict) else {}
    if base.get("warehouse_variants"):
        return base
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return base
    row = db.query(Product).filter(Product.id == pid).first()
    if row is None:
        return base
    if getattr(row, "is_warehouse_clearance", False):
        enrich_standalone_warehouse_product(db, base, row)
        base["is_warehouse_clearance"] = True
        base["product_id"] = getattr(row, "product_id", None) or base.get("product_id")
        if row.sizes is not None:
            base["sizes"] = row.sizes
        if row.colors is not None:
            base["colors"] = row.colors
    else:
        enrich_parent_with_warehouse_clearance(db, base, row)
    return base


def enrich_listing_product_payloads(
    db: Session,
    pairs: List[Tuple[Any, Dict[str, Any]]],
) -> None:
    """Gắn warehouse_variants / warehouse_clearance cho thẻ SP danh sách & trang chủ."""
    enrich_listing_product_payloads_batched(db, pairs)


def enrich_listing_product_payloads_batched(
    db: Session,
    pairs: List[Tuple[Any, Dict[str, Any]]],
) -> None:
    """Một lần đọc settings + query kho theo batch base_sku (tránh N+1 trên lưới gợi ý)."""
    if not pairs:
        return
    enabled, pct = get_warehouse_clearance_settings(db)
    base_skus: List[str] = []
    seen_bases: Set[str] = set()
    for row, _payload in pairs:
        if row is None or getattr(row, "is_warehouse_clearance", False):
            continue
        base = _resolve_base_sku_for_parent(row)
        if base and base not in seen_bases:
            seen_bases.add(base)
            base_skus.append(base)
    wh_by_base = _list_warehouse_variants_for_base_skus(db, base_skus) if base_skus else {}

    for row, payload in pairs:
        if row is None or not isinstance(payload, dict):
            continue
        if getattr(row, "is_warehouse_clearance", False):
            enrich_standalone_warehouse_product(db, payload, row)
            payload["group_listing_path"] = WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH
            continue
        source_oos = is_source_product_oos(row)
        payload["source_oos"] = source_oos
        base = _resolve_base_sku_for_parent(row)
        variants: List[Dict[str, Any]] = []
        if base:
            for wh in wh_by_base.get(base, []):
                if int(wh.available or 0) <= 0:
                    continue
                variants.append(warehouse_variant_payload(db, wh))
        payload["warehouse_variants"] = variants
        payload["warehouse_clearance"] = {
            "enabled": enabled or len(variants) > 0,
            "discount_percent": pct,
        }


def _list_warehouse_variants_for_base_skus(
    db: Session,
    base_skus: List[str],
    *,
    active_only: bool = True,
) -> Dict[str, List[Product]]:
    cleaned = [str(s or "").strip() for s in base_skus if str(s or "").strip()]
    if not cleaned:
        return {}
    conditions = []
    for sku in cleaned:
        conditions.append(Product.base_sku == sku)
        conditions.append(Product.product_id.like(f"{sku}/%"))
    q = db.query(Product).filter(Product.is_warehouse_clearance == True)  # noqa: E712
    if active_only:
        q = q.filter(Product.is_active == True)  # noqa: E712
    rows = q.filter(or_(*conditions)).order_by(Product.product_id.asc()).all()
    grouped: Dict[str, List[Product]] = {sku: [] for sku in cleaned}
    for row in rows:
        base = _resolve_base_sku_for_parent(row) or (row.base_sku or "").strip()
        if not base:
            pid = (row.product_id or "").split("/")[0].strip()
            base = pid
        if base in grouped:
            grouped[base].append(row)
    return grouped


def enrich_parent_with_warehouse_clearance(db: Session, payload: Dict[str, Any], product: Product) -> None:
    if getattr(product, "is_warehouse_clearance", False):
        return
    base = _resolve_base_sku_for_parent(product)
    source_oos = is_source_product_oos(product)
    payload["source_oos"] = source_oos
    enabled, pct = get_warehouse_clearance_settings(db)
    variants: List[Dict[str, Any]] = []
    if base:
        for wh in list_warehouse_variants_for_base_sku(db, base):
            if int(wh.available or 0) <= 0:
                continue
            variants.append(warehouse_variant_payload(db, wh))
    payload["warehouse_variants"] = variants
    payload["warehouse_clearance"] = {
        "enabled": enabled or len(variants) > 0,
        "discount_percent": pct,
    }


def _normalize_excel_colors(colors: Any) -> List[Dict[str, Any]]:
    if not colors:
        return []
    if isinstance(colors, list):
        out: List[Dict[str, Any]] = []
        for item in colors:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("value") or "").strip()
                img = str(item.get("img") or item.get("image") or "").strip()
                if name or img:
                    entry: Dict[str, Any] = {}
                    if name:
                        entry["name"] = name
                        entry["value"] = name
                    if img:
                        entry["img"] = img
                    out.append(entry)
            elif isinstance(item, str) and item.strip():
                label = item.strip()
                out.append({"name": label, "value": label})
        return out
    return []


def _extract_variant_image_urls(colors: Any) -> List[str]:
    urls: List[str] = []
    for item in _normalize_excel_colors(colors):
        img = str(item.get("img") or "").strip()
        if img and img not in urls:
            urls.append(img)
    return urls


def _gallery_image_pool(parent: Product) -> List[str]:
    """Ảnh SP gốc: colors[].img → gallery → images → main_image."""
    urls: List[str] = []
    seen: Set[str] = set()

    def add(u: str) -> None:
        t = str(u or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        urls.append(t)

    for item in _normalize_excel_colors(getattr(parent, "colors", None)):
        img = str(item.get("img") or item.get("image") or "").strip()
        if img:
            add(img)
    for field in (getattr(parent, "gallery", None), getattr(parent, "images", None)):
        if isinstance(field, list):
            for u in field:
                if isinstance(u, str):
                    add(u)
    mi = getattr(parent, "main_image", None)
    if mi:
        add(str(mi))
    return urls


def _apply_excel_variant_media(product_data: Dict[str, Any], colors: Any) -> None:
    """Ảnh dòng kho lấy từ variant (colors[].img)."""
    urls = _extract_variant_image_urls(colors)
    if not urls:
        return
    product_data["main_image"] = urls[0]
    product_data["images"] = urls


def _apply_parent_media_fallback(product_data: Dict[str, Any], parent: Product) -> None:
    """Khi variant không có img — dùng thư viện ảnh SP gốc."""
    if (product_data.get("main_image") or "").strip():
        return
    pool = _gallery_image_pool(parent)
    if not pool:
        return
    product_data["main_image"] = pool[0]
    product_data["images"] = pool[:12]
    if not product_data.get("gallery"):
        product_data["gallery"] = pool[:24]


def _normalize_color_match_key(name: str) -> str:
    s = str(name or "").strip().lower()
    s = re.sub(r"\s*\(\d+\)\s*$", "", s).strip()
    return s


def resolve_parent_color_entry(
    parent: Product,
    *,
    color_name: Optional[str] = None,
    color_index: Optional[int] = None,
    color_image: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Chọn ô màu SP gốc (theo index hoặc tên) kèm URL ảnh nếu có."""
    normalized = _normalize_excel_colors(getattr(parent, "colors", None))
    pool = _gallery_image_pool(parent)

    if color_index is not None and color_index >= 0:
        if color_index < len(normalized):
            entry = dict(normalized[color_index])
            if not entry.get("img") and color_index < len(pool):
                entry["img"] = pool[color_index]
            if color_image:
                entry["img"] = str(color_image).strip()
            return entry
        if color_index < len(pool):
            label = (
                str(normalized[0].get("name") or "Như ảnh").strip()
                if normalized
                else "Như ảnh"
            )
            suffix = f" ({color_index + 1})" if len(pool) > 1 else ""
            return {"name": f"{label}{suffix}", "value": label, "img": pool[color_index]}

    if color_image:
        label = str(color_name or "Như ảnh").strip() or "Như ảnh"
        return {"name": label, "value": label, "img": str(color_image).strip()}

    key = _normalize_color_match_key(color_name or "")
    if key:
        for i, item in enumerate(normalized):
            nm = _normalize_color_match_key(
                str(item.get("name") or item.get("value") or "")
            )
            if nm == key:
                entry = dict(item)
                if not entry.get("img") and i < len(pool):
                    entry["img"] = pool[i]
                return entry

    if normalized:
        entry = dict(normalized[0])
        if not entry.get("img") and pool:
            entry["img"] = pool[0]
        return entry
    if pool:
        return {"name": "Như ảnh", "value": "Như ảnh", "img": pool[0]}
    return None


def expand_parent_colors_for_intake(parent: Product) -> List[Dict[str, Any]]:
    """
    Danh sách màu cho UI nhập hoàn — mở rộng theo gallery khi SP chỉ có 1 nhãn «như ảnh».
    """
    normalized = _normalize_excel_colors(getattr(parent, "colors", None))
    pool = _gallery_image_pool(parent)
    out: List[Dict[str, Any]] = []

    if len(pool) > 1 and len(normalized) <= 1:
        base_label = (
            str(normalized[0].get("name") or normalized[0].get("value") or "Như ảnh").strip()
            if normalized
            else "Như ảnh"
        )
        for i, url in enumerate(pool):
            name = f"{base_label} ({i + 1})" if len(pool) > 1 else base_label
            out.append(
                {
                    "key": f"idx:{i}",
                    "name": name,
                    "image": url,
                    "color_index": i,
                }
            )
        return out

    if len(pool) > 1 and not normalized:
        for i, url in enumerate(pool):
            out.append(
                {
                    "key": f"idx:{i}",
                    "name": f"Như ảnh ({i + 1})" if len(pool) > 1 else "Như ảnh",
                    "image": url,
                    "color_index": i,
                }
            )
        return out

    for i, item in enumerate(normalized):
        name = str(item.get("name") or item.get("value") or "").strip() or f"Màu {i + 1}"
        img = str(item.get("img") or item.get("image") or "").strip()
        if not img and i < len(pool):
            img = pool[i]
        display = name
        if len(normalized) > 1:
            dup = sum(
                1
                for x in normalized
                if _normalize_color_match_key(str(x.get("name") or x.get("value") or ""))
                == _normalize_color_match_key(name)
            )
            if dup > 1:
                display = f"{name} ({i + 1})"
        out.append(
            {
                "key": f"idx:{i}",
                "name": display,
                "image": img or None,
                "color_index": i,
            }
        )
    return out


_WAREHOUSE_INTAKE_MEDIA_FIELDS = (
    "main_image",
    "images",
    "gallery",
    "video_link",
    "link_default",
)


def merge_return_intake_from_parent(
    parent: Product,
    product_data: Dict[str, Any],
    parsed: Dict[str, Any],
    *,
    color_name: Optional[str] = None,
    color_index: Optional[int] = None,
    color_image: Optional[str] = None,
) -> None:
    """Nhập hoàn từ SP gốc — clone đủ field + ảnh/màu biến thể như import kho."""
    color_entry = resolve_parent_color_entry(
        parent,
        color_name=color_name,
        color_index=color_index,
        color_image=color_image,
    )
    if color_entry:
        product_data["colors"] = [color_entry]
        product_data["color"] = str(
            color_entry.get("name") or color_entry.get("value") or ""
        ).strip() or None

    merge_clone_from_parent(parent, product_data, parsed)

    for field in _WAREHOUSE_INTAKE_MEDIA_FIELDS:
        val = getattr(parent, field, None)
        if val is not None and val != [] and val != "":
            product_data[field] = val

    if color_entry:
        product_data["colors"] = [color_entry]
        cn = str(color_entry.get("name") or color_entry.get("value") or "").strip()
        if cn:
            product_data["color"] = cn

    _apply_excel_variant_media(product_data, product_data.get("colors"))
    _apply_parent_media_fallback(product_data, parent)

    attach_warehouse_row_to_parent(product_data, parent)


def resolve_parent_base_sku(parent: Product) -> str:
    """Mã SKU gốc để gắn dòng kho — ưu tiên code (H9441), không dùng product_id dài."""
    code = (getattr(parent, "code", None) or "").strip()
    if code and "/" not in code:
        return code
    pid = (getattr(parent, "product_id", None) or "").strip()
    if pid and "/" not in pid:
        return pid
    parsed = parse_warehouse_product_id(pid)
    if parsed:
        return str(parsed.get("base_sku") or "").strip()
    return code or pid


def attach_warehouse_row_to_parent(product_data: Dict[str, Any], parent: Product) -> None:
    """Gắn dòng kho thanh lý với SP gốc (base_sku + metadata + slug PDP gốc)."""
    base = resolve_parent_base_sku(parent)
    if base:
        product_data["base_sku"] = base
    pid = str(product_data.get("product_id") or "").strip()
    if pid:
        product_data["code"] = pid
    parent_slug = (parent.slug or "").strip()
    pi_raw = product_data.get("product_info")
    pi: Dict[str, Any] = dict(pi_raw) if isinstance(pi_raw, dict) else {}
    pi["parent_product_id"] = (getattr(parent, "product_id", None) or "").strip()
    pi["parent_code"] = (getattr(parent, "code", None) or "").strip() or base
    pi["linked_to_parent"] = True
    if parent_slug:
        pi["parent_slug"] = parent_slug
    product_data["product_info"] = pi


def backfill_warehouse_row_from_parent(
    row: Product,
    parent: Product,
    *,
    color_name: Optional[str] = None,
    color_index: Optional[int] = None,
) -> bool:
    """Bổ sung ảnh/mô tả thiếu trên dòng kho đã tạo (in-place)."""
    changed = False
    product_data: Dict[str, Any] = {}
    parsed = parse_warehouse_product_id(getattr(row, "product_id", None)) or {
        "base_sku": (row.base_sku or row.code or "").strip(),
        "warehouse_color": color_name or row.color,
        "warehouse_size": (row.sizes or [None])[0] if row.sizes else None,
    }
    merge_return_intake_from_parent(
        parent,
        product_data,
        parsed,
        color_name=color_name or (row.color or None),
        color_index=color_index,
    )
    for field in list(_WAREHOUSE_CLONE_FIELDS) + list(_WAREHOUSE_INTAKE_MEDIA_FIELDS):
        if field == "name":
            continue
        new_val = product_data.get(field)
        if new_val is None or new_val == [] or new_val == "":
            continue
        old_val = getattr(row, field, None)
        if old_val is None or old_val == [] or old_val == "":
            setattr(row, field, new_val)
            changed = True
    if not (row.main_image or "").strip() and product_data.get("main_image"):
        row.main_image = product_data["main_image"]
        changed = True
    if not (row.images or []) and product_data.get("images"):
        row.images = product_data["images"]
        changed = True
    if not (row.gallery or []) and product_data.get("gallery"):
        row.gallery = product_data["gallery"]
        changed = True
    if product_data.get("colors") and (
        not row.colors or not _extract_variant_image_urls(row.colors)
    ):
        row.colors = product_data["colors"]
        if product_data.get("color"):
            row.color = product_data["color"]
        changed = True
    if not row.is_warehouse_clearance:
        row.is_warehouse_clearance = True
        changed = True
    if parent is not None:
        base = resolve_parent_base_sku(parent)
        if base and (row.base_sku or "").strip() != base:
            row.base_sku = base
            changed = True
        attach_warehouse_row_to_parent(product_data, parent)
        if product_data.get("product_info"):
            row.product_info = product_data["product_info"]
            changed = True
        if row.product_id and (row.code or "") != row.product_id:
            row.code = row.product_id
            changed = True
        if parent.price is not None:
            try:
                parent_price = float(parent.price)
                if parent_price > 0 and float(row.price or 0) != parent_price:
                    row.price = parent_price
                    changed = True
            except (TypeError, ValueError):
                pass
    return changed


def _apply_warehouse_variant_fields(
    product_data: Dict[str, Any],
    parsed: Dict[str, Any],
    *,
    excel_sizes: Any = None,
    excel_colors: Any = None,
) -> None:
    wh_size = parsed.get("warehouse_size")
    wh_color = parsed.get("warehouse_color")

    sizes_from_excel: List[str] = []
    if isinstance(excel_sizes, list):
        sizes_from_excel = [str(s).strip() for s in excel_sizes if str(s).strip()]
    elif product_data.get("sizes") and isinstance(product_data.get("sizes"), list):
        sizes_from_excel = [str(s).strip() for s in product_data["sizes"] if str(s).strip()]

    if sizes_from_excel:
        product_data["sizes"] = sizes_from_excel
    elif wh_size:
        product_data["sizes"] = [str(wh_size)]
    elif product_data.get("sizes") and isinstance(product_data.get("sizes"), list):
        fallback = [str(s).strip() for s in product_data["sizes"] if str(s).strip()]
        if fallback:
            product_data["sizes"] = fallback

    colors_from_excel = _normalize_excel_colors(excel_colors if excel_colors is not None else product_data.get("colors"))
    if colors_from_excel:
        product_data["colors"] = colors_from_excel
        first_name = str(colors_from_excel[0].get("name") or colors_from_excel[0].get("value") or "").strip()
        if first_name:
            product_data["color"] = first_name
    elif wh_color:
        product_data["color"] = wh_color
        product_data["colors"] = [{"name": wh_color, "value": wh_color}]
    elif (product_data.get("color") or "").strip():
        label = str(product_data["color"]).strip()
        product_data["colors"] = [{"name": label, "value": label}]

    product_data["is_warehouse_clearance"] = True
    product_data["base_sku"] = parsed["base_sku"]
    pid = str(product_data.get("product_id") or "").strip()
    if pid:
        product_data["code"] = pid
    product_data["is_active"] = True
    product_data["source_stock_status"] = "unknown"


def apply_warehouse_import_from_row(product_data: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """Chưa có SP gốc — dữ liệu file + metadata kho (validate danh mục ở bulk import)."""
    excel_sizes = product_data.get("sizes")
    excel_colors = product_data.get("colors")
    _apply_warehouse_variant_fields(
        product_data,
        parsed,
        excel_sizes=excel_sizes,
        excel_colors=excel_colors,
    )
    _apply_excel_variant_media(product_data, product_data.get("colors"))


def merge_clone_from_parent(parent: Product, product_data: Dict[str, Any], parsed: Dict[str, Any]) -> None:
    """
    Có SP gốc: clone mọi field từ gốc; chỉ Excel cung cấp size, Variant (màu+ảnh), tồn.
    Giá list = giá SP gốc (% giảm áp lúc hiển thị theo cài đặt admin sale).
    """
    excel_sizes = product_data.get("sizes")
    excel_colors = product_data.get("colors")
    excel_available = product_data.get("available")

    for field in _WAREHOUSE_CLONE_FIELDS:
        if hasattr(parent, field):
            product_data[field] = getattr(parent, field)

    _apply_warehouse_variant_fields(
        product_data,
        parsed,
        excel_sizes=excel_sizes,
        excel_colors=excel_colors,
    )
    _apply_excel_variant_media(product_data, product_data.get("colors"))

    if parent.price is not None:
        product_data["price"] = parent.price

    if excel_available is not None:
        product_data["available"] = excel_available


def enrich_standalone_warehouse_product(db: Session, payload: Dict[str, Any], product: Product) -> None:
    """PDP trực tiếp dòng kho khi chưa có SP gốc cùng base_sku."""
    enabled, pct = get_warehouse_clearance_settings(db)
    base = resolve_warehouse_list_price(db, product)
    if base <= 0:
        base = float(getattr(product, "price", None) or payload.get("price") or 0)
    pricing = apply_clearance_pricing(base, percent=pct)
    payload["price"] = pricing["display_price"]
    payload["original_price"] = pricing["original_price"] if pricing["savings_amount"] > 0 else None
    payload["is_warehouse_clearance"] = True
    payload["site_sale"] = None
    payload["source_oos"] = False
    payload["warehouse_variants"] = []
    payload["warehouse_clearance"] = {
        "enabled": enabled,
        "discount_percent": pct,
    }
    variant_img = (warehouse_variant_payload(db, product).get("color_image") or "").strip()
    if variant_img:
        payload["main_image"] = variant_img
        colors = payload.get("colors")
        if isinstance(colors, list) and colors:
            first = colors[0]
            if isinstance(first, dict):
                first["img"] = variant_img
            elif isinstance(first, str):
                payload["colors"] = [{"name": first, "value": first, "img": variant_img}]
        else:
            payload["colors"] = [{"name": "Như ảnh", "value": "Như ảnh", "img": variant_img}]


def assert_product_deletion_allowed(db: Session, product: Product, *, admin_force: bool = False) -> None:
    """Raise ValueError với message tiếng Việt nếu không được xóa."""
    if getattr(product, "is_warehouse_clearance", False):
        if not admin_force and int(product.available or 0) > 0:
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


def parent_has_deletion_block(db: Session, product: Product, *, admin_force: bool = False) -> Optional[str]:
    try:
        assert_product_deletion_allowed(db, product, admin_force=admin_force)
        return None
    except ValueError as exc:
        return str(exc)
