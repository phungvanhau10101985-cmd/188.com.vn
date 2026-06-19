"""
Feed TSV (tab-separated) cho Google Merchant Center — primary product data source.

Định dạng: https://support.google.com/merchants/answer/160567

Luôn xuất các cột `sale_price` và `sale_price_effective_date` (header cố định — map một lần trên
Merchant Center). Khi chưa có chương trình giảm giá, hai cột để trống; khi bật sale có thể điền
từ `.env` `CATALOG_SALE_*` (tạm thời) hoặc sau này nối nguồn campaign khác vào `_sale_price_and_effective`.

`product_info` (AK) dùng cho: google_product_category, gender, custom_label, cogs,
`auto_pricing_min_price`, …
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, Optional
from urllib.parse import quote, unquote, urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product

_VN_TZ = timezone(timedelta(hours=7))

# --- Google Merchant primary feed (header = tên thuộc tính GMC) ---
# sale_price / sale_price_effective_date: luôn có trong TSV (ô trống khi chưa giảm giá).

TSV_COLUMNS = (
    "id",
    "title",
    "description",
    "link",
    "mobile_link",
    "image_link",
    "additional_image_link",
    "availability",
    "price",
    "custom_label_0",
    "custom_label_1",
    "custom_label_2",
    "custom_label_3",
    "custom_label_4",
    "sale_price",
    "sale_price_effective_date",
    "cost_of_goods_sold",
    "auto_pricing_min_price",
    "brand",
    "condition",
    "identifier_exists",
    "gtin",
    "mpn",
    "google_product_category",
    "product_type",
    "gender",
    "age_group",
    "color",
    "size",
    "material",
    "shipping_weight",
    "item_group_id",
    "video",
)


def _is_blankish(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null"}:
        return True
    return False


def _strip_html(text: Optional[str], max_len: int = 5000) -> str:
    if _is_blankish(text):
        return ""
    plain = re.sub(r"<[^>]+>", " ", str(text))
    plain = re.sub(r"\s+", " ", plain).strip()
    if len(plain) > max_len:
        plain = plain[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return plain


def _tsv_cell(s: Optional[str]) -> str:
    if _is_blankish(s):
        return ""
    t = str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def _abs_url(site_base: str, path_or_url: Optional[str]) -> str:
    """Chuẩn hoá URL ảnh / link đầy đủ HTTPS."""
    if _is_blankish(path_or_url):
        return ""
    u = str(path_or_url).strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = site_base.rstrip("/")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return base + u
    return f"{base}/{u}"


def _pick_main_image(product: Product, site_base: str) -> str:
    mi = getattr(product, "main_image", None)
    if mi:
        return _abs_url(site_base, mi)
    imgs = product.images if isinstance(product.images, list) else []
    if imgs and len(imgs) > 0:
        first = imgs[0]
        if isinstance(first, dict):
            first = first.get("url") or first.get("src") or first.get("image") or ""
        return _abs_url(site_base, str(first)) if first else ""
    return ""


def _pick_additional_images(product: Product, site_base: str) -> str:
    """Ảnh phụ: chỉ từ gallery_images (Product.images); bỏ ảnh đầu."""
    imgs: list[str] = []
    raw = product.images if isinstance(product.images, list) else []
    for i, item in enumerate(raw):
        if i == 0:
            continue
        url = ""
        if isinstance(item, dict):
            url = item.get("url") or item.get("src") or item.get("image") or ""
        elif item:
            url = str(item)
        if url:
            imgs.append(_abs_url(site_base, url))
        if len(imgs) >= 10:
            break
    return ",".join(imgs)


def _feed_path_segment_from_slug(raw_slug: str, fallback: str) -> str:
    """
    Slug trên DB đôi khi lưu cả URL PDP (https://…/products/segment) hoặc chuỗi đã encode.
    Trả về một segment path an toàn cho /products/{segment} (khớp frontend productPathSlugFromApi).
    """
    s = (raw_slug or "").strip()
    if not s:
        return (fallback or "").strip()
    for _ in range(4):
        low = s.lower()
        if low.startswith("http://") or low.startswith("https://"):
            break
        if "%" not in s:
            break
        try:
            d = unquote(s)
        except Exception:
            break
        if d == s:
            break
        s = d
    if s.startswith("/products/"):
        part = s.split("/products/", 1)[-1].split("?")[0].split("#")[0].strip("/").split("/")[0]
        return unquote(part) if part else (fallback or "").strip()
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        try:
            u = urlparse(s)
            segs = [x for x in u.path.split("/") if x]
            if "products" in segs:
                i = segs.index("products")
                if i + 1 < len(segs):
                    return unquote(segs[i + 1])
            if segs:
                return unquote(segs[-1])
        except Exception:
            return (fallback or "").strip()
        return (fallback or "").strip()
    return s


def _product_canonical_link(product: Product, shop_base_url: str) -> str:
    """URL trang chi tiết trên shop (Merchant/Meta/TikTok). Không dùng `link_default` — trường đó là URL nguồn NCC (1688/Taobao)."""
    base = shop_base_url.rstrip("/")
    raw_slug = "" if _is_blankish(getattr(product, "slug", None)) else str(getattr(product, "slug", "")).strip()
    raw_pid = getattr(product, "product_id", None)
    pid = str(product.id) if _is_blankish(raw_pid) else str(raw_pid).strip()
    path = _feed_path_segment_from_slug(raw_slug, pid) if raw_slug else pid
    if _is_blankish(path):
        path = pid
    return f"{base}/products/{quote(path, safe='')}"


def _availability(product: Product) -> str:
    av = getattr(product, "available", None)
    try:
        n = int(av) if av is not None else 0
    except (TypeError, ValueError):
        n = 0
    return "in_stock" if n > 0 else "out_of_stock"


def _price_gmc(price: Optional[float], currency: str) -> str:
    try:
        p = float(price) if price is not None else 0.0
        if math.isnan(p):
            p = 0.0
    except (TypeError, ValueError):
        p = 0.0
    cur = (currency or "VND").upper().strip()
    if cur == "VND":
        amt = max(0, int(round(p)))
        return f"{amt} {cur}"
    return f"{p:.2f} {cur}"


def _custom_label_0_by_price(price: Optional[float]) -> str:
    try:
        p = float(price) if price is not None else math.nan
        if math.isnan(p):
            return "Nhãn tùy chỉnh 0"
    except (TypeError, ValueError):
        return "Nhãn tùy chỉnh 0"
    tiers = (
        (400000, "Nhãn tùy chỉnh 1"),
        (700000, "Nhãn tùy chỉnh 2"),
        (1000000, "Nhãn tùy chỉnh 3"),
        (1300000, "Nhãn tùy chỉnh 4"),
        (1600000, "Nhãn tùy chỉnh 5"),
        (1900000, "Nhãn tùy chỉnh 6"),
        (2200000, "Nhãn tùy chỉnh 7"),
        (2500000, "Nhãn tùy chỉnh 8"),
        (2800000, "Nhãn tùy chỉnh 9"),
        (300000000, "Nhãn tùy chỉnh 10"),
    )
    for max_price, label in tiers:
        if p <= max_price:
            return label
    return ""


def _product_type_breadcrumb(product: Product) -> str:
    parts = []
    for attr in ("category", "subcategory", "sub_subcategory"):
        v = getattr(product, attr, None)
        if not _is_blankish(v):
            parts.append(str(v).strip())
    breadcrumb = " > ".join(parts)
    if getattr(product, "is_warehouse_clearance", False):
        label = "Hàng thanh lý kho"
        return f"{label} > {breadcrumb}" if breadcrumb else label
    return breadcrumb


def _sizes_string(product: Product) -> str:
    s = getattr(product, "sizes", None)
    if _is_blankish(s):
        return ""
    if isinstance(s, list):
        bits = []
        for x in s[:30]:
            if isinstance(x, dict):
                bits.append(str(x.get("name") or x.get("label") or x.get("size") or x))
            else:
                bits.append(str(x))
        return ", ".join(bits)
    if isinstance(s, str):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                return ", ".join(str(x) for x in data[:30])
        except json.JSONDecodeError:
            pass
        return s.strip()[:300]
    return str(s)[:300]


def _weight_value(product: Product) -> str:
    w = getattr(product, "weight", None)
    if _is_blankish(w):
        return ""
    s = str(w).strip()
    if not s:
        return ""
    low = s.lower()
    if any(x in low for x in ("kg", "g", "lb", "oz", "gram")):
        return _tsv_cell(s)
    return _tsv_cell(f"{s} kg")


def _gtin_from_product_info(product: Product) -> str:
    pi = getattr(product, "product_info", None)
    if not isinstance(pi, dict):
        return ""
    return _tsv_cell(str(pi.get("gtin") or pi.get("GTIN") or ""))


# --- product_info (AK) & feed enrichment ---

def _product_info_dict(product: Product) -> dict:
    raw = getattr(product, "product_info", None)
    return raw if isinstance(raw, dict) else {}


def _gmt_instant_from_date_string(val: object, *, end_of_day: bool = False) -> str:
    """Một điểm thời gian theo GMC (GMT+7, không có : trong offset)."""
    if _is_blankish(val):
        return ""
    s = str(val).strip()
    day = s[:10]
    if len(day) < 10 or day[4] != "-" or day[7] != "-":
        return ""
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return ""
    t = "23:59" if end_of_day else "00:00"
    return f"{day}T{t}+0700"


def _list_price_for_feed(product: Product) -> float:
    """Giá gốc (`price`) — dùng tính giá sale khi có chương trình env."""
    try:
        p = float(getattr(product, "price", None) or 0)
        if math.isnan(p):
            return 0.0
        return max(0.0, p)
    except (TypeError, ValueError):
        return 0.0


def _today_vn() -> date:
    return datetime.now(_VN_TZ).date()


def _parse_iso_date(val: object) -> Optional[date]:
    if val is None or _is_blankish(val):
        return None
    s = str(val).strip()[:10]
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _catalog_sale_program_enabled_now() -> bool:
    if not getattr(settings, "CATALOG_SALE_ACTIVE", False):
        return False
    try:
        pct = float(getattr(settings, "CATALOG_SALE_DISCOUNT_PERCENT", 0) or 0)
    except (TypeError, ValueError):
        return False
    if pct <= 0:
        return False
    ds = _parse_iso_date(getattr(settings, "CATALOG_SALE_START", "") or "")
    de = _parse_iso_date(getattr(settings, "CATALOG_SALE_END", "") or "")
    today = _today_vn()
    if ds is None and de is None:
        return True
    if ds is not None and today < ds:
        return False
    if de is not None and today > de:
        return False
    return True


def _catalog_sale_effective_gmc_string() -> str:
    ds = _parse_iso_date(getattr(settings, "CATALOG_SALE_START", "") or "")
    de = _parse_iso_date(getattr(settings, "CATALOG_SALE_END", "") or "")
    if ds and de:
        a = _gmt_instant_from_date_string(ds.isoformat(), end_of_day=False)
        b = _gmt_instant_from_date_string(de.isoformat(), end_of_day=True)
        if a and b:
            return f"{a}/{b}"
    if ds and not de:
        a = _gmt_instant_from_date_string(ds.isoformat(), end_of_day=False)
        b = _gmt_instant_from_date_string(ds.isoformat(), end_of_day=True)
        if a and b:
            return f"{a}/{b}"
    if de and not ds:
        a = _gmt_instant_from_date_string(de.isoformat(), end_of_day=False)
        b = _gmt_instant_from_date_string(de.isoformat(), end_of_day=True)
        if a and b:
            return f"{a}/{b}"
    return ""


def _sale_price_and_effective(
    product: Product,
    currency: str,
    *,
    sale_state=None,
    db: Optional[Session] = None,
) -> tuple[str, str]:
    """sale_price từ lịch sale ngày trùng tháng (ưu tiên) hoặc CATALOG_SALE_* env."""
    base = _list_price_for_feed(product)
    if base <= 0:
        return "", ""

    if sale_state is None and db is not None:
        from app.services import sale_calendar as sale_calendar_svc

        sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)

    if sale_state is not None and getattr(sale_state, "is_active", False):
        from app.services import sale_calendar as sale_calendar_svc

        return sale_calendar_svc.feed_sale_price_tuple(
            base,
            sale_state,
            currency,
            format_price_fn=_price_gmc,
            effective_gmc_fn=lambda s, e: sale_calendar_svc.gmc_effective_from_bounds(s, e),
        )

    if not _catalog_sale_program_enabled_now():
        return "", ""

    try:
        pct = float(getattr(settings, "CATALOG_SALE_DISCOUNT_PERCENT", 0) or 0)
    except (TypeError, ValueError):
        pct = 0.0
    pct = max(0.0, min(100.0, pct))
    if pct <= 0:
        return "", ""

    sale_raw = base * (1.0 - pct / 100.0)
    cur = (currency or "VND").upper().strip()
    if cur == "VND":
        sale_raw = max(0.0, float(round(sale_raw)))
    else:
        sale_raw = max(0.0, sale_raw)

    if sale_raw >= base - 1e-6:
        return "", ""

    sale_str = _price_gmc(sale_raw, currency)
    eff = _catalog_sale_effective_gmc_string()
    return sale_str, _tsv_cell(eff) if eff else ""


def _cost_of_goods_sold(product: Product, currency: str) -> str:
    pi = _product_info_dict(product)
    raw = pi.get("cost_of_goods_sold") or pi.get("cogs")
    if _is_blankish(raw):
        if getattr(settings, "GOOGLE_AUTOMATED_DISCOUNT_FEED_AUTO_OPT_IN", False):
            base = _list_price_for_feed(product)
            if base > 0:
                pct = float(getattr(settings, "GOOGLE_AUTOMATED_DISCOUNT_DEFAULT_COGS_PERCENT", 65) or 65)
                pct = max(5.0, min(95.0, pct))
                return _price_gmc(base * (pct / 100.0), currency)
        return ""
    try:
        fp = float(raw)
        return _price_gmc(fp, currency)
    except (TypeError, ValueError):
        return _tsv_cell(str(raw))


def _auto_pricing_min_price(product: Product, currency: str, *, cogs_gmc: str) -> str:
    """Giá tối thiểu cho chiết khấu tự động Google — bắt buộc kèm COGS."""
    if _is_blankish(cogs_gmc):
        return ""

    base = _list_price_for_feed(product)
    if base <= 0:
        return ""

    pi = _product_info_dict(product)
    raw = pi.get("auto_pricing_min_price") or pi.get("google_auto_pricing_min_price")
    min_raw: Optional[float] = None
    if not _is_blankish(raw):
        try:
            min_raw = float(raw)
        except (TypeError, ValueError):
            min_raw = None

    if min_raw is None:
        if not getattr(settings, "GOOGLE_AUTOMATED_DISCOUNT_FEED_AUTO_OPT_IN", False):
            return ""
        pct = float(getattr(settings, "GOOGLE_AUTOMATED_DISCOUNT_DEFAULT_MIN_PRICE_PERCENT", 95) or 95)
        pct = max(5.0, min(95.0, pct))
        min_raw = base * (pct / 100.0)

    if min_raw is None or min_raw <= 0:
        return ""

    # Parse COGS numeric from GMC string "650000 VND"
    cogs_num = 0.0
    try:
        cogs_num = float(str(cogs_gmc).split()[0])
    except (TypeError, ValueError, IndexError):
        cogs_num = 0.0

    min_raw = max(min_raw, cogs_num + 1.0)
    min_raw = min(min_raw, base * 0.95)
    if min_raw >= base:
        return ""
    return _price_gmc(min_raw, currency)


def _custom_label_0_value(product: Product) -> str:
    pi = _product_info_dict(product)
    o = pi.get("custom_label_0")
    if not _is_blankish(o):
        return _tsv_cell(str(o))
    return _custom_label_0_by_price(getattr(product, "price", None))


def _optional_custom_label(product: Product, n: int) -> Optional[str]:
    pi = _product_info_dict(product)
    o = pi.get(f"custom_label_{n}")
    if not _is_blankish(o):
        return _tsv_cell(str(o))
    return None


def _custom_labels_1_to_4(product: Product) -> tuple[str, str, str, str]:
    style = _tsv_cell(getattr(product, "style", None)) or ""
    occ = _tsv_cell(getattr(product, "occasion", None)) or ""
    sub = _tsv_cell(getattr(product, "subcategory", None)) or ""
    pur = getattr(product, "purchases", 0) or 0
    try:
        purn = int(pur)
    except (TypeError, ValueError):
        purn = 0
    tier = ""
    if purn >= 100:
        tier = "high_demand"
    elif purn >= 20:
        tier = "moving"
    l1 = _optional_custom_label(product, 1) or style
    l2 = _optional_custom_label(product, 2) or occ
    l3 = _optional_custom_label(product, 3) or tier
    l4 = _optional_custom_label(product, 4) or sub
    return (l1, l2, l3, l4)


def _normalized_gender(product: Product) -> str:
    pi = _product_info_dict(product)
    g = str(pi.get("gender") or "").strip().lower()
    if not g:
        return ""
    if g in ("male", "m", "nam"):
        return "male"
    if g in ("female", "f", "nữ", "nu"):
        return "female"
    if g in ("unisex", "unisexual"):
        return "unisex"
    if g in ("male", "female", "unisex"):
        return g
    return ""


def _normalized_age_group(product: Product) -> str:
    pi = _product_info_dict(product)
    a = str(pi.get("age_group") or "").strip().lower()
    valid = {"newborn", "infant", "toddler", "kids", "adult"}
    if a in valid:
        return a
    vi_map = {
        "trẻ em": "kids",
        "tre em": "kids",
        "trẻ sơ sinh": "newborn",
        "người lớn": "adult",
        "nguoi lon": "adult",
    }
    return vi_map.get(a, "")


def _item_group_id_value(product: Product) -> str:
    pi = _product_info_dict(product)
    for key in ("item_group_id", "item_group"):
        v = pi.get(key)
        if not _is_blankish(v):
            return _tsv_cell(str(v))
    return ""


def _video_feed_url(product: Product) -> str:
    """URL video đầy đủ (YouTube/Direct); ưu tiên cột video_link + product_info."""
    pi = _product_info_dict(product)
    v = getattr(product, "video_link", None) or pi.get("video_link") or pi.get("video_url") or pi.get("video")
    if _is_blankish(v):
        return ""
    s = str(v).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return _tsv_cell(s)
    return ""


def resolved_google_product_category(product: Product, default_from_settings: str) -> str:
    """Dùng cho Google/Meta/TikTok: product_info trước, env fallback, sau đó breadcrumb."""
    pi = _product_info_dict(product)
    for key in ("google_product_category", "gmc_category", "google_product_cat"):
        v = pi.get(key)
        if not _is_blankish(v):
            return _tsv_cell(str(v))
    if not _is_blankish(default_from_settings):
        return _tsv_cell(str(default_from_settings).strip())
    return _tsv_cell(_product_type_breadcrumb(product))


def merchant_row_values(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    sale_state=None,
    db: Optional[Session] = None,
) -> list[str]:
    from app.services import sale_calendar as sale_calendar_svc

    if sale_state is None and db is not None:
        sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)

    raw_title = getattr(product, "name", "") or ""
    title = _tsv_cell(sale_calendar_svc.feed_title_with_sale_prefix(raw_title, sale_state) if sale_state else raw_title)
    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"
    link = _product_canonical_link(product, shop_base_url)
    gtin = _gtin_from_product_info(product)
    mpn = _tsv_cell(getattr(product, "code", None) or "")
    identifier = "yes" if (gtin or mpn) else "no"
    gdefault = getattr(settings, "CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY", "") or ""
    gcat = resolved_google_product_category(product, gdefault)
    sale_price, sale_eff = _sale_price_and_effective(product, currency, sale_state=sale_state, db=db)
    c0 = _custom_label_0_value(product)
    if sale_state is not None:
        sale_label = sale_calendar_svc.feed_custom_label_for_teaser(sale_state)
        if sale_label:
            c0 = _tsv_cell(sale_label)
    c1, c2, c3, c4 = _custom_labels_1_to_4(product)
    gender = _normalized_gender(product)
    age_grp = _normalized_age_group(product)
    ig = _item_group_id_value(product)
    vid = _video_feed_url(product)
    cogs = _cost_of_goods_sold(product, currency)
    auto_min = _auto_pricing_min_price(product, currency, cogs_gmc=cogs)

    return [
        _tsv_cell(getattr(product, "product_id", "") or ""),
        title,
        _strip_html(getattr(product, "description", None)),
        link,
        link,
        _pick_main_image(product, image_site_base),
        _pick_additional_images(product, image_site_base),
        _availability(product),
        _price_gmc(getattr(product, "price", None), currency),
        c0,
        c1,
        c2,
        c3,
        c4,
        sale_price,
        sale_eff,
        cogs,
        auto_min,
        brand,
        "new",
        identifier,
        gtin,
        mpn,
        gcat,
        _product_type_breadcrumb(product),
        gender,
        age_grp,
        _tsv_cell(getattr(product, "color", None)),
        _sizes_string(product),
        _tsv_cell(getattr(product, "material", None)),
        _weight_value(product),
        ig,
        vid,
    ]


def merchant_feed_header_row() -> str:
    return "\t".join(TSV_COLUMNS)


def merchant_feed_line_for_product(
    product: Product,
    shop_base_url: str,
    image_site_base: str,
    currency: str,
    *,
    sale_state=None,
    db: Optional[Session] = None,
) -> str:
    vals = merchant_row_values(
        product,
        shop_base_url,
        image_site_base,
        currency,
        sale_state=sale_state,
        db=db,
    )
    return "\t".join(vals)


def iter_merchant_feed_lines(
    db: Session,
    shop_base_url: str,
    *,
    currency: str = "VND",
    image_site_base: str | None = None,
    only_active: bool = True,
    yield_per: int = 1000,
) -> Iterator[str]:
    """Stream từng dòng feed (header + rows)."""
    from app.services import sale_calendar as sale_calendar_svc

    img_base = (image_site_base or shop_base_url).rstrip("/")
    sale_state = sale_calendar_svc.resolve_sale_calendar_state(db)
    yield merchant_feed_header_row()
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    q = db.query(Product).order_by(Product.id)
    if only_active:
        q = q.filter(Product.is_active.is_(True))
    q = apply_catalog_visibility_filter(q)
    for p in q.yield_per(max(50, yield_per)):
        yield merchant_feed_line_for_product(
            p,
            shop_base_url,
            img_base,
            currency,
            sale_state=sale_state,
            db=db,
        )
