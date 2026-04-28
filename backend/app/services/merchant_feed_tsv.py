"""

Feed TSV (tab-separated) cho Google Merchant Center — primary product data source.

Định dạng: https://support.google.com/merchants/answer/160567

Các cột: theo đặc tả sản phẩm phổ biến, trường rỗng nếu không có trong DB.

"""

from __future__ import annotations



import json

import re

from typing import Iterator, Optional



from sqlalchemy.orm import Session



from app.models.product import Product



# Danh sách đầu đủ các thuộc tính thường dùng trong feed Merchant Center (TSV một dòng header)

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

    "sale_price",

    "sale_price_effective_date",

    "cost_of_goods_sold",

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

)





def _strip_html(text: Optional[str], max_len: int = 5000) -> str:

    if not text:

        return ""

    plain = re.sub(r"<[^>]+>", " ", str(text))

    plain = re.sub(r"\s+", " ", plain).strip()

    if len(plain) > max_len:

        plain = plain[: max_len - 1].rsplit(" ", 1)[0] + "…"

    return plain





def _tsv_cell(s: Optional[str]) -> str:

    if s is None:

        return ""

    t = str(s).replace("\t", " ").replace("\r", " ").replace("\n", " ")

    return re.sub(r"\s+", " ", t).strip()





def _abs_url(site_base: str, path_or_url: Optional[str]) -> str:

    """Chuẩn hoá URL ảnh / link đầy đủ HTTPS."""

    if not path_or_url:

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

    imgs: list = []

    raw = product.images if isinstance(product.images, list) else []

    for i, item in enumerate(raw):

        if i == 0:

            continue

        url = ""

        if isinstance(item, dict):

            url = item.get("url") or item.get("src") or ""

        elif item:

            url = str(item)

        if url:

            imgs.append(_abs_url(site_base, url))

        if len(imgs) >= 10:

            break

    gal = product.gallery if isinstance(product.gallery, list) else []

    for item in gal:

        if len(imgs) >= 10:

            break

        url = ""

        if isinstance(item, dict):

            url = item.get("url") or item.get("src") or ""

        elif item:

            url = str(item)

        u = _abs_url(site_base, url) if url else ""

        if u and u not in imgs:

            imgs.append(u)

    return ",".join(imgs)





def _product_canonical_link(product: Product, shop_base_url: str) -> str:

    base = shop_base_url.rstrip("/")

    ld = getattr(product, "link_default", None)

    if ld and (str(ld).startswith("http://") or str(ld).startswith("https://")):

        return str(ld).strip()

    slug = getattr(product, "slug", None) or ""

    slug = slug.strip()

    pid = getattr(product, "product_id", None) or str(product.id)

    path = slug if slug else str(pid).strip()

    return f"{base}/products/{path}"





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

    except (TypeError, ValueError):

        p = 0.0

    cur = (currency or "VND").upper().strip()

    if cur == "VND":

        amt = max(0, int(round(p)))

        return f"{amt} {cur}"

    return f"{p:.2f} {cur}"





def _product_type_breadcrumb(product: Product) -> str:

    parts = []

    for attr in ("category", "subcategory", "sub_subcategory"):

        v = getattr(product, attr, None)

        if v and str(v).strip():

            parts.append(str(v).strip())

    return " > ".join(parts)





def _sizes_string(product: Product) -> str:

    s = getattr(product, "sizes", None)

    if s is None:

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

    if w is None:

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





def merchant_row_values(

    product: Product,

    shop_base_url: str,

    image_site_base: str,

    currency: str,

) -> list[str]:

    title = _tsv_cell(getattr(product, "name", "") or "")

    brand = _tsv_cell(getattr(product, "brand_name", "") or "") or "188"



    link = _product_canonical_link(product, shop_base_url)

    gtin = _gtin_from_product_info(product)

    mpn = _tsv_cell(getattr(product, "code", None) or "")

    identifier = "yes" if (gtin or mpn) else "no"



    return [

        _tsv_cell(getattr(product, "product_id", "") or ""),

        title,

        _strip_html(getattr(product, "description", None)),

        link,

        link,  # mobile_link: cùng trang responsive

        _pick_main_image(product, image_site_base),

        _pick_additional_images(product, image_site_base),

        _availability(product),

        _price_gmc(getattr(product, "price", None), currency),

        "",  # sale_price

        "",  # sale_price_effective_date

        "",  # cost_of_goods_sold — thường không gửi hoặc chỉ khi chính sách

        brand,

        "new",

        identifier,

        gtin,

        mpn,

        "",  # google_product_category — nên bổ sung theo taxonomy trong MC nếu cần

        _product_type_breadcrumb(product),

        "",  # gender

        "",  # age_group

        _tsv_cell(getattr(product, "color", None)),

        _sizes_string(product),

        _tsv_cell(getattr(product, "material", None)),

        _weight_value(product),

    ]





def merchant_feed_header_row() -> str:

    return "\t".join(TSV_COLUMNS)





def merchant_feed_line_for_product(

    product: Product,

    shop_base_url: str,

    image_site_base: str,

    currency: str,

) -> str:

    vals = merchant_row_values(product, shop_base_url, image_site_base, currency)

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

    """

    Stream từng dòng feed (bao gồm dòng header). yield_per để không nạp cả cỡ vào RAM.

    """

    img_base = (image_site_base or shop_base_url).rstrip("/")

    yield merchant_feed_header_row()



    q = db.query(Product).order_by(Product.id)

    if only_active:

        q = q.filter(Product.is_active.is_(True))



    for p in q.yield_per(max(50, yield_per)):

        yield merchant_feed_line_for_product(p, shop_base_url, img_base, currency)


