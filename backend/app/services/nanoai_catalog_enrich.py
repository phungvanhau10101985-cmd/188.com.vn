# Bổ sung giá / màu từ catalog nội bộ cho kết quả NanoAI (theo product_id hoặc sku).
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.product import Product as ProductModel


def _slug_from_product_url(url: Any) -> Optional[str]:
    """Lấy slug trang chi tiết /products/{slug} từ URL tuyệt đối hoặc path."""
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if not u:
        return None
    try:
        path = urlparse(u).path if "://" in u else u
    except Exception:
        path = u
    m = re.search(r"/products/([^/?#]+)", path)
    if not m:
        return None
    return unquote(m.group(1).strip()) or None


def _format_price_hint_vnd(amount: float) -> str:
    n = int(round(float(amount)))
    return f"{n} VND"


def _truthy_price_hint(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return True


def _truthy_str(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    return bool(val)


def _color_image_urls_from_row(row: ProductModel) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        t = (u or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        urls.append(t)

    raw_colors = row.colors
    if isinstance(raw_colors, list):
        for item in raw_colors:
            if isinstance(item, dict):
                img = item.get("img")
                if img:
                    add(str(img))
    for field in (row.gallery, row.images):
        if isinstance(field, list):
            for u in field:
                if isinstance(u, str):
                    add(u)
    mi = row.main_image
    if mi and str(mi).strip():
        add(str(mi).strip())
    return urls[:20]


def _normalize_product_dict(p: Dict[str, Any]) -> None:
    # Partner có thể trả snake_case hoặc camelCase; chuẩn hóa một trường trước khi enrich / trả JSON.
    variants = p.get("color_variants")
    if variants is None and isinstance(p.get("colorVariants"), list):
        variants = p.get("colorVariants")
    if not isinstance(variants, list):
        variants = []

    variant_urls: List[str] = []
    variant_names: List[str] = []
    cleaned_variants: List[Dict[str, Any]] = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        img_raw = v.get("img") or v.get("image_url") or v.get("image")
        name_raw = v.get("name")
        rec: Dict[str, Any] = {}
        if name_raw is not None and str(name_raw).strip():
            nm = str(name_raw).strip()
            rec["name"] = nm
            variant_names.append(nm)
        if img_raw is not None and str(img_raw).strip():
            im = str(img_raw).strip()
            rec["img"] = im
            variant_urls.append(im)
        if rec:
            cleaned_variants.append(rec)
    p["color_variants"] = cleaned_variants
    p.pop("colorVariants", None)

    urls = p.get("color_image_urls")
    if not isinstance(urls, list):
        urls = None
    if urls is None:
        alt = p.get("colorImageUrls")
        if isinstance(alt, list):
            urls = alt
    if urls is None or not isinstance(urls, list):
        base: List[str] = []
    else:
        base = [str(u).strip() for u in urls if u and str(u).strip()]
    p.pop("colorImageUrls", None)

    seen_urls = set(base)
    for u in variant_urls:
        if u not in seen_urls:
            seen_urls.add(u)
            base.append(u)
    p["color_image_urls"] = base[:24]

    if variant_names and not _truthy_str(p.get("color_display")):
        uniq_n: List[str] = []
        seen_n: set[str] = set()
        for n in variant_names:
            k = n.lower()
            if k not in seen_n:
                seen_n.add(k)
                uniq_n.append(n)
        p["color_display"] = ", ".join(uniq_n[:6])


def _color_display(row: ProductModel) -> Optional[str]:
    c = row.color
    if c and str(c).strip():
        return str(c).strip()
    raw = row.colors
    if not raw or not isinstance(raw, list):
        return None
    names: List[str] = []
    for item in raw:
        if isinstance(item, dict):
            n = item.get("name") or item.get("value")
            if n:
                names.append(str(n).strip())
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    if not names:
        return None
    seen = set()
    uniq = []
    for n in names:
        key = n.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(n)
    return ", ".join(uniq[:6])


def enrich_nanoai_products(db: Session, products: List[Any]) -> None:
    if not products:
        return
    for p in products:
        if isinstance(p, dict):
            _normalize_product_dict(p)

    ids: set[str] = set()
    codes: set[str] = set()
    slugs: set[str] = set()
    for p in products:
        if not isinstance(p, dict):
            continue
        inv = p.get("inventory_id")
        if inv is not None and str(inv).strip():
            ids.add(str(inv).strip())
        sku = p.get("sku")
        if sku is not None and str(sku).strip():
            codes.add(str(sku).strip())
        slug = _slug_from_product_url(p.get("product_url"))
        if slug:
            slugs.add(slug)
    conditions = []
    if ids:
        conditions.append(ProductModel.product_id.in_(list(ids)))
    codes_lower = list({str(c).strip().lower() for c in codes if str(c).strip()})
    if codes_lower:
        conditions.append(func.lower(ProductModel.code).in_(codes_lower))
    if slugs:
        conditions.append(ProductModel.slug.in_(list(slugs)))
    if not conditions:
        return
    rows = db.query(ProductModel).filter(or_(*conditions)).all()
    by_pid: Dict[str, ProductModel] = {str(r.product_id).strip(): r for r in rows if r.product_id}
    by_code: Dict[str, ProductModel] = {}
    by_slug: Dict[str, ProductModel] = {}
    for r in rows:
        if r.code and str(r.code).strip():
            k = str(r.code).strip().lower()
            if k not in by_code:
                by_code[k] = r
        if r.slug and str(r.slug).strip():
            s = str(r.slug).strip()
            if s not in by_slug:
                by_slug[s] = r

    for p in products:
        if not isinstance(p, dict):
            continue
        row: Optional[ProductModel] = None
        inv = str(p.get("inventory_id") or "").strip()
        sku = str(p.get("sku") or "").strip()
        slug = _slug_from_product_url(p.get("product_url"))
        if inv and inv in by_pid:
            row = by_pid[inv]
        elif sku:
            row = by_code.get(sku.lower())
        if row is None and slug and slug in by_slug:
            row = by_slug[slug]
        if row is None:
            continue
        price = row.price
        if price is not None:
            p["price"] = float(price)
            if not _truthy_price_hint(p.get("price_hint")):
                p["price_hint"] = _format_price_hint_vnd(float(price))
        cd = _color_display(row)
        if cd:
            p["color_display"] = cd
        # Gộp ảnh variant/gallery từ kho: luôn giữ URL NanoAI trước, thêm ảnh kho (dedupe).
        extra = _color_image_urls_from_row(row)
        if extra:
            cur = p.get("color_image_urls")
            if not isinstance(cur, list):
                cur = []
            seen = {str(u).strip() for u in cur if u}
            out = list(cur)
            for u in extra:
                t = str(u).strip()
                if t and t not in seen:
                    seen.add(t)
                    out.append(t)
            p["color_image_urls"] = out[:24]


def enrich_nanoai_response_body(db: Session, body: Any) -> Any:
    if not isinstance(body, dict):
        return body
    prods = body.get("products")
    if isinstance(prods, list):
        enrich_nanoai_products(db, prods)
    return body
