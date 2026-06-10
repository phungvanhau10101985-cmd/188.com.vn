from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.services.alicdn_urls import normalize_product_image_url
from app.utils.product_synthetic_engagement import synthetic_engagement_counts


class Import1688Error(RuntimeError):
    pass


def _offer_id_from_query(query: str) -> Optional[str]:
    """Đọc offerId không phân biệt hoa thường (detail PC/Mobile thường dùng offerId=)."""
    if not query:
        return None
    for key, vals in parse_qs(query).items():
        if (key or "").lower() != "offerid":
            continue
        for raw in vals or []:
            v = (raw or "").strip()
            if v:
                return v
    return None


def canonical_1688_offer_pc_url(offer_id: str) -> str:
    """URL chi tiết PC chuẩn để scrape / cột link (khớp luồng Hibox abb-* → detail.1688)."""
    oid = str(offer_id or "").strip()
    if oid.isdigit():
        return f"https://detail.1688.com/offer/{oid}.html"
    return ""


def extract_offer_id(url: str) -> Optional[str]:
    from app.services.import_hibox_scraper import normalize_product_import_url

    norm = normalize_product_import_url((url or "").strip())
    parsed = urlparse(norm)
    qs_offer = _offer_id_from_query(parsed.query)
    if qs_offer:
        return qs_offer
    match = re.search(r"/offer/(\d+)\.html", parsed.path or "", re.I)
    if match:
        return match.group(1)
    return None


def extract_1688_numeric_offer_id(url: str, fallback_offer_id: Optional[str] = None) -> Optional[str]:
    """Chỉ ID offer dạng số (detail 1688 `/offer/<digits>.html` hoặc `?offerId=`)."""
    oid = extract_offer_id(url)
    if oid and oid.isdigit():
        return oid
    fb = (fallback_offer_id or "").strip()
    if fb.isdigit():
        return fb
    return None


def build_canonical_1688_product_id(offer_digits: str, sku_code: str = "") -> str:
    """
    Mã nội bộ web theo nguồn 1688: A + offerId.
    Không ghép `a188` / SKU trong luồng lấy thông tin sản phẩm.
    """
    oid = str(offer_digits or "").strip()
    if not oid.isdigit():
        raise ValueError("offer id 1688 phải là chuỗi chữ số.")
    return f"A{oid}"


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        v = (value or "").strip()
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _normalize_image_url(url: str) -> str:
    u = (url or "").strip().strip('"').strip("'")
    if not u:
        return ""
    return normalize_product_image_url(u)


def _prefer_larger_offer_image(url: str) -> str:
    """Thử nâng kích cỡ ảnh thumb 1688 (220/310 → 720) nếu path có chứa các token kích cỡ."""
    u = url or ""
    if not u:
        return ""
    pairs = (
        ("220x220", "720x720"),
        ("310x310", "720x720"),
        ("490x490", "790x790"),
    )
    for sm, lg in pairs:
        if sm in u:
            return u.replace(sm, lg, 1)
    return u


def _normalize_playwright_cookie(item: Dict[str, Any]) -> Dict[str, Any]:
    cookie = dict(item)
    cookie.setdefault("domain", ".1688.com")
    cookie.setdefault("path", "/")
    # Playwright does not require sameSite for imported cookies. Browser exporters use
    # inconsistent values (for example no_restriction), so omit it to avoid rejection.
    cookie.pop("sameSite", None)
    return cookie


def _load_cookie_json() -> List[Dict[str, Any]]:
    raw = settings.IMPORT_1688_COOKIE_JSON
    if not raw and settings.IMPORT_1688_COOKIE_FILE:
        path = Path(settings.IMPORT_1688_COOKIE_FILE)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []

    # Cho phép cả JSON export từ browser lẫn chuỗi cookie "a=b; c=d".
    if raw.lstrip().startswith(("[", "{")):
        data = json.loads(raw)
        cookies = data.get("cookies") if isinstance(data, dict) else data
        if not isinstance(cookies, list):
            raise Import1688Error("IMPORT_1688_COOKIE_JSON phải là list cookie hoặc object có key cookies.")
        normalized = []
        for c in cookies:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            normalized.append(_normalize_playwright_cookie(c))
        return normalized

    cookies = []
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            cookies.append({"name": name, "value": value.strip(), "domain": ".1688.com", "path": "/"})
    return cookies


def _looks_like_company_h1(text: str) -> bool:
    """1688 hay đặt <h1> là tên công ty — không dùng làm tên sản phẩm."""
    t = (text or "").strip()
    return bool(re.search(r"有限公司|有限责任公司|个体工商户", t))


def _clean_doc_title(raw: str) -> str:
    text = re.sub(r"\s+", " ", str(raw or "")).strip()
    text = re.sub(r"\s*[-–—]\s*阿里巴巴\s*$", "", text, flags=re.I).strip()
    text = re.sub(r"[-_\s]*(阿里巴巴|\s*1688)\s*$", "", text, flags=re.I).strip(" -_")
    return text[:500]


def _pick_title(payload: Dict[str, Any]) -> str:
    structured = payload.get("structured") or {}
    ts = structured.get("title_candidates") if isinstance(structured, dict) else None
    if isinstance(ts, list):
        for value in ts:
            text = _clean_doc_title(str(value or ""))
            text = re.sub(r"[-_]?阿里巴巴1688.*$", "", text).strip(" -_")
            if text and len(text) > 4 and not _looks_like_company_h1(text):
                return text[:500]

    meta = _clean_doc_title(payload.get("meta_title") or "")
    if meta and len(meta) > 4 and not _looks_like_company_h1(meta):
        return meta[:500]

    doc = _clean_doc_title(payload.get("document_title") or "")
    if doc and len(doc) > 4 and not _looks_like_company_h1(doc):
        return doc[:500]

    h1_raw = payload.get("h1") or ""
    h1 = re.sub(r"\s+", " ", str(h1_raw)).strip()
    h1 = re.sub(r"[-_]?阿里巴巴1688.*$", "", h1).strip(" -_")
    if h1 and len(h1) > 4 and not _looks_like_company_h1(h1):
        return h1[:500]

    nodes = payload.get("title_nodes") or []
    if isinstance(nodes, list):
        best = ""
        for n in nodes:
            line = ""
            if isinstance(n, str):
                line = re.sub(r"\s+", " ", n).strip()
            elif isinstance(n, dict):
                line = re.sub(r"\s+", " ", str((n.get("text") or n.get("label") or ""))).strip()
            if not line or len(line) < 12:
                continue
            if _looks_like_company_h1(line):
                continue
            if "\n关注\n" in line or "入驻" in line:
                continue
            if ("复购率" in line or "¥" in line) and len(line) < 220:
                if len(line) > len(best):
                    best = line
            elif len(line) > len(best) and "http" not in line:
                best = line
        if best:
            first = best.split("\n")[0].strip()
            head = first if len(first) >= 8 else ""
            if head and not _looks_like_company_h1(head):
                return head[:500]

    if doc:
        return doc[:500]
    if h1 and len(h1) > 4:
        return h1[:500]
    return ""


_JUNK_IMG_HOST = ("dmtracking.1688.com",)


def _is_junk_product_image_url(url: str) -> bool:
    u = (url or "").lower()
    if not u:
        return True
    for h in _JUNK_IMG_HOST:
        if h in u:
            return True
    if "gw.alicdn.com/mt/" in u:
        return True
    if "/tfs/tb1" in u and "-80-80.png" in u:
        return True
    if re.search(r"tps-\d+-\d+\.(png|jpg|webp)(\?|$)", u):
        # sprite / icon grids on cdn (common small assets)
        m = re.search(r"tps-(\d+)-(\d+)\.", u)
        if m and int(m.group(1)) <= 96 and int(m.group(2)) <= 96:
            return True
    # tiny placeholder dimensions in Ali path
    if re.search(r"[-_/](\d{1,3})[-_](\d{1,3})\.png(?:\?|$)", u):
        m = re.search(r"[-_/](\d{1,3})[-_](\d{1,3})\.png(?:\?|$)", u)
        if m and int(m.group(1)) <= 80 and int(m.group(2)) <= 80:
            return True
    return False


def _image_product_priority(url: str) -> Tuple[int, int]:
    """(tier, negative length) — nhỏ hơn sort trước; tier thấp = ưu tiên ảnh SP thật."""
    u = url or ""
    if _is_junk_product_image_url(u):
        return (99, 0)
    if "cbu01.alicdn.com/img/ibank" in u:
        return (0, -len(u))
    if "img.alicdn.com/imgextra/" in u and u.lower().endswith((".jpg", ".jpeg", ".webp")):
        return (1, -len(u))
    if "img.alicdn.com/imgextra/" in u and ".png" in u.lower():
        return (2, -len(u))
    if "img.alicdn.com" in u:
        return (4, -len(u))
    return (5, -len(u))


def _sort_product_images(urls: List[str]) -> List[str]:
    scored = [( _image_product_priority(u), u) for u in urls]
    scored.sort(key=lambda x: x[0])
    return [u for _, u in scored]


def _extract_images_regex(text: str, max_images: int) -> List[str]:
    patterns = [
        r'https?:\\/\\/[^\"\'<> ]+?\.(?:jpg|jpeg|png|webp)',
        r'//[^\"\'<> ]+?\.(?:jpg|jpeg|png|webp)',
        r'https?://[^\"\'<> ]+?\.(?:jpg|jpeg|png|webp)',
    ]
    found: List[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, flags=re.I))
    images = []
    for img in found:
        img = img.replace("\\/", "/")
        img = _normalize_image_url(img)
        if not img:
            continue
        if ("alicdn.com" not in img) and ("1688.com" not in img):
            continue
        if _is_junk_product_image_url(img):
            continue
        images.append(img)
    deduped = _dedupe(images)
    ranked = _sort_product_images(deduped)
    return ranked[:max_images]


_SKU_IMAGE_FROM_JSON = re.compile(r'"imageUrl"\s*:\s*"(https?:[^"]+)"', re.I)
_SKU_CONSIGN_PRICE = re.compile(r'"consignPrice"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?', re.I)
_SKU_AMOUNT = re.compile(r'"skuAmount"\s*:\s*"([^"]*)"', re.I)


def _extract_sku_signals_from_scripts(scripts_concat: str) -> Dict[str, Any]:
    from_json = _dedupe(
        [_normalize_image_url(m.group(1)) for m in _SKU_IMAGE_FROM_JSON.finditer(scripts_concat)]
    )
    ibank: List[str] = []
    for m in re.finditer(
        r"https://cbu01\.alicdn\.com/img/ibank/[^\"\s\\<>]+\.(?:jpg|jpeg|webp)", scripts_concat, re.I
    ):
        ibank.append(_normalize_image_url(m.group(0)))

    image_urls = _dedupe(ibank + from_json)
    image_urls = [u for u in image_urls if u and not _is_junk_product_image_url(u)]
    image_urls = _sort_product_images(image_urls)

    prices: List[float] = []
    for m in _SKU_CONSIGN_PRICE.finditer(scripts_concat):
        try:
            v = float(m.group(1))
            if 0 < v < 1_000_000:
                prices.append(v)
        except (TypeError, ValueError):
            pass

    sizes: List[str] = []
    for m in _SKU_AMOUNT.finditer(scripts_concat):
        amt = (m.group(1) or "").strip()
        if not amt or amt in sizes:
            continue
        if len(amt) <= 4 and re.match(r"^[0-9]{2,4}$", amt):
            sizes.append(amt)
    sizes = sizes[:80]

    return {"sku_images": image_urls, "sku_prices": prices, "sku_amount_labels": sizes}


def _extract_body_specs(body_text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"colors_label": [], "sizes_label": [], "article_no": ""}
    if not body_text:
        return out
    m = re.search(r"颜色[：:\t\s]*([\u4e00-\u9fffA-Za-z0-9，、,\s/+]+)", body_text)
    if m:
        raw = m.group(1).strip().split("\n")[0]
        parts = re.split(r"[、,，+/]\s*", raw)
        out["colors_label"] = _dedupe([p.strip() for p in parts if p.strip()][:30])
    m2 = re.search(r"尺码[：:\t\s]*([0-9A-Za-z\s，、,.-]+)", body_text)
    if m2:
        raw2 = m2.group(1).strip().split("\n")[0]
        parts2 = re.split(r"[、,，/\s]+\s*", raw2)
        out["sizes_label"] = _dedupe([p.strip() for p in parts2 if p.strip()][:60])
    m3 = re.search(r"货号[：:\t\s]*([A-Za-z0-9_-]+)", body_text)
    if m3:
        out["article_no"] = m3.group(1).strip()[:120]
    return out


def _merge_sizes_plausible(dom_sizes: List[str], sku_sizes: List[str], body_sizes: List[str]) -> List[str]:
    """Ưu tiên dòng 尺码 trong body + DOM SKU; chỉ giữ số trong khoảng thường gặp (giày 26–53) để giảm nhiễu."""
    body_num = [s for s in body_sizes if s.isdigit()]
    dom_num = [s for s in dom_sizes if s.isdigit()]
    sku_num = [s for s in sku_sizes if s.isdigit()]
    cand = body_num[:] if len(body_num) >= 2 else _dedupe(dom_num + sku_num + body_num)
    out: List[str] = []
    for s in cand:
        try:
            n = int(s)
        except ValueError:
            continue
        if 26 <= n <= 53:
            out.append(s)
    dedup = _dedupe(out)
    if dedup:
        return dedup
    fallback = [
        str(x).strip()
        for x in (body_sizes + dom_sizes + sku_sizes)
        if str(x).strip()
    ]
    return _dedupe(fallback)[:80]


def _extract_price(text: str) -> Tuple[float, Optional[str], Optional[str]]:
    candidates = []
    for pattern in (
        r'"consignPrice"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
        r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)"?',
        r'"priceRange"\s*:\s*"?([0-9.]+)\s*[-~]\s*([0-9.]+)"?',
        r'¥\s*([0-9]+(?:\.[0-9]+)?)',
    ):
        for match in re.finditer(pattern, text, flags=re.I):
            nums = [x for x in match.groups() if x]
            candidates.extend(nums)
    parsed = []
    for c in candidates:
        try:
            value = float(c)
            if 0 < value < 1_000_000:
                parsed.append(value)
        except (TypeError, ValueError):
            pass
    if not parsed:
        return 0.0, None, None
    lo = min(parsed)
    hi = max(parsed)
    return lo, str(lo), str(hi) if hi != lo else str(lo)


def _extract_shop(payload: Dict[str, Any], text: str) -> Tuple[Optional[str], Optional[str]]:
    shop_name = payload.get("shop_name")
    shop_id = None
    for pattern in (r'"sellerLoginId"\s*:\s*"([^"]+)"', r'"loginId"\s*:\s*"([^"]+)"'):
        match = re.search(pattern, text)
        if match and not shop_name:
            shop_name = match.group(1)
            break
    id_match = re.search(r'"sellerUserId"\s*:\s*"?([0-9]+)"?', text)
    if id_match:
        shop_id = id_match.group(1)
    return (str(shop_name).strip()[:200] if shop_name else None, shop_id)


def normalize_1688_payload(source_url: str, offer_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    html = payload.get("html_sample") or ""
    scripts_parts = payload.get("scripts") or []
    scripts_text = "\n".join(scripts_parts[:120] if isinstance(scripts_parts, list) else [])
    combined = f"{html}\n{scripts_text}"
    structured = payload.get("structured") if isinstance(payload.get("structured"), dict) else {}

    sku_sig = _extract_sku_signals_from_scripts(scripts_text)
    body_specs = _extract_body_specs(payload.get("body_text") or "")

    title = _pick_title(payload) or f"Sản phẩm 1688 {offer_id or ''}".strip()

    carousel = [_normalize_image_url(u) for u in (structured.get("carousel_images") or []) if u]
    detail_dom = [_normalize_image_url(u) for u in (structured.get("detail_images") or []) if u]
    swatches = [_normalize_image_url(u) for u in (structured.get("color_swatch_images") or []) if u]

    regex_pool = _extract_images_regex(combined, max(settings.IMPORT_1688_MAX_IMAGES * 3, 48))
    sku_json_imgs = [_normalize_image_url(u) for u in (sku_sig.get("sku_images") or []) if u]

    def _filt(urls: List[str]) -> List[str]:
        return [u for u in urls if u and not _is_junk_product_image_url(u)]

    carousel = _filt(carousel)
    detail_dom = _filt(detail_dom)
    swatches = [_prefer_larger_offer_image(u) for u in _filt(swatches)]
    regex_pool = _filt(regex_pool)
    sku_json_imgs = _filt(sku_json_imgs)
    carousel = [_prefer_larger_offer_image(u) for u in carousel]
    detail_dom = [_prefer_larger_offer_image(u) for u in detail_dom]
    sku_json_imgs = [_prefer_larger_offer_image(u) for u in sku_json_imgs]
    regex_pool = [_prefer_larger_offer_image(u) for u in regex_pool]

    max_main = settings.IMPORT_1688_MAX_IMAGES
    seen_main: set = set()
    main_ordered: List[str] = []

    def _take(urls: List[str]) -> None:
        for u in _sort_product_images(urls):
            if u in seen_main:
                continue
            seen_main.add(u)
            main_ordered.append(u)
            if len(main_ordered) >= max_main:
                return

    _take(carousel)
    _take(swatches)
    _take(sku_json_imgs)
    if len(main_ordered) < 6:
        _take(regex_pool)

    gallery_candidates: List[str] = []
    for u in detail_dom:
        if u not in seen_main:
            gallery_candidates.append(u)
    for u in regex_pool:
        if u not in seen_main and u not in gallery_candidates:
            gallery_candidates.append(u)
    gallery_sorted = _sort_product_images(gallery_candidates)[: max(max_main * 2, 32)]
    main_ordered = _dedupe(main_ordered)
    gallery_sorted = _dedupe(gallery_sorted)

    swatches_for_export = _dedupe(swatches)[:max_main]
    carousel_only_for_export = _dedupe(_sort_product_images(carousel))[:max_main]
    if not carousel_only_for_export:
        sw_excl = set(swatches_for_export)
        pick = [u for u in main_ordered if u not in sw_excl]
        if not pick:
            pick = list(main_ordered)
        carousel_only_for_export = pick[:max_main]
    detail_block_only: List[str] = []
    for u in _sort_product_images(detail_dom):
        if u in seen_main:
            continue
        detail_block_only.append(u)
    detail_block_only = _dedupe(detail_block_only)[: max(max_main * 3, 64)]

    price, lower, higher = _extract_price(combined)
    extra_px = sku_sig.get("sku_prices") or []
    if isinstance(extra_px, list) and extra_px:
        merged_px: List[float] = []
        for x in extra_px:
            try:
                if isinstance(x, (int, float)):
                    merged_px.append(float(x))
                elif isinstance(x, str) and x.strip():
                    merged_px.append(float(x.strip()))
            except (TypeError, ValueError):
                pass
        merged_px = [x for x in merged_px if 0 < x < 1_000_000]
        if merged_px:
            lo_f = min(merged_px)
            hi_f = max(merged_px)
            if price and price > 0:
                lo_f = min(lo_f, price)
                hi_f = max(hi_f, price)
            elif price and price <= 0:
                pass
            price = float(lo_f)
            lower = str(lo_f)
            higher = str(hi_f) if hi_f != lo_f else str(lo_f)

    dom_main_raw = structured.get("main_price_cny")
    try:
        if isinstance(dom_main_raw, (int, float)):
            dom_piece = float(dom_main_raw)
        elif isinstance(dom_main_raw, str) and str(dom_main_raw).strip():
            dom_piece = float(str(dom_main_raw).strip())
        else:
            dom_piece = 0.0
    except (TypeError, ValueError):
        dom_piece = 0.0
    # Giá khối OD 「1件起批」 — tránh merge SKU/script lấy nhầm mức ≥N件 thấp hơn hoặc ¥ trong body (ship…).
    if 0 < dom_piece < 1_000_000:
        price = dom_piece
        band: List[float] = [dom_piece]
        for raw in (lower, higher):
            try:
                v = float(str(raw).strip())
                if 0 < v < 1_000_000:
                    band.append(v)
            except (TypeError, ValueError):
                pass
        lo_b = min(band)
        hi_b = max(band)
        lower = str(lo_b)
        higher = str(hi_b) if hi_b != lo_b else str(lo_b)

    shop_name, shop_id = _extract_shop(payload, combined)

    meta_desc = (payload.get("meta_description") or "").strip()
    description = meta_desc[:2000] if meta_desc else (payload.get("description") or title)

    dom_sizes = structured.get("size_labels") or []
    dom_sizes_list: List[str] = []
    if isinstance(dom_sizes, list):
        dom_sizes_list = [str(x).strip() for x in dom_sizes if str(x).strip()]

    merged_sizes = _merge_sizes_plausible(
        dom_sizes_list,
        list(sku_sig.get("sku_amount_labels") or []),
        list(body_specs["sizes_label"]),
    )

    color_names = list(body_specs["colors_label"])

    dom_color_variants_raw = structured.get("color_variants") or []
    dom_color_pairs: List[Dict[str, Optional[str]]] = []
    if isinstance(dom_color_variants_raw, list):
        first_main = main_ordered[0] if main_ordered else None
        n_dom_color_labels = sum(
            1
            for x in dom_color_variants_raw
            if isinstance(x, dict) and str(x.get("label") or "").strip()
        )
        for row in dom_color_variants_raw:
            if not isinstance(row, dict):
                continue
            lab = str(row.get("label") or "").strip()
            if not lab:
                continue
            img_raw = row.get("image_url")
            img = _normalize_image_url(str(img_raw).strip()) if img_raw else ""
            if img and _is_junk_product_image_url(img):
                img = ""
            if not img and first_main and n_dom_color_labels == 1:
                img = first_main
            nu = _prefer_larger_offer_image(img) if img else ""
            dom_color_pairs.append({"label": lab, "image_url": nu or None})

    variants: Dict[str, Any] = {"source": "1688"}
    if merged_sizes:
        variants["sizes"] = merged_sizes
    if dom_color_pairs:
        variants["color_swatches"] = dom_color_pairs
        color_names = _dedupe([str(p["label"]) for p in dom_color_pairs if p.get("label")])
        sw_from_pairs: List[str] = []
        for p in dom_color_pairs:
            u = p.get("image_url")
            if not u:
                continue
            nu = _normalize_image_url(str(u))
            if nu and not _is_junk_product_image_url(nu):
                sw_from_pairs.append(_prefer_larger_offer_image(nu))
        if sw_from_pairs:
            swatches_for_export = _dedupe(sw_from_pairs)[:max_main]
    elif swatches:
        pairs: List[Dict[str, Optional[str]]] = []
        if len(color_names) == len(swatches):
            pairs = [{"label": a, "image_url": b} for a, b in zip(color_names, swatches)]
        else:
            for i, img in enumerate(swatches):
                lab = color_names[i] if i < len(color_names) else None
                pairs.append({"label": lab, "image_url": img})
        variants["color_swatches"] = pairs
    elif color_names:
        variants["colors"] = color_names

    specifications: Dict[str, Any] = dict(payload.get("specifications") or {})
    specifications.setdefault("尺码", ",".join(merged_sizes) if merged_sizes else "")
    specifications.setdefault("颜色", "、".join(color_names) if color_names else "")
    if body_specs.get("article_no"):
        specifications.setdefault("货号", body_specs["article_no"])

    product_info = {
        "product_info": {
            "source": "1688",
            "source_offer_id": offer_id,
            "source_url": source_url,
            "name_original": title,
            "article_no": body_specs.get("article_no") or "",
        },
        "market_info": {
            "currency": "CNY",
            "source_price": price,
            "price_cny_low": lower,
            "price_cny_high": higher if higher and lower != higher else higher,
            "shop_name": shop_name,
            "shop_id": shop_id,
        },
        "specifications": specifications,
        "variants": variants,
    }

    colors_out = color_names[:] if color_names else [p.get("label") for p in variants.get("color_swatches") or [] if p.get("label")]
    colors_out = [c for c in colors_out if c]

    main_image = main_ordered[0] if main_ordered else None

    _eng = synthetic_engagement_counts()

    return {
        "product_id": build_canonical_1688_product_id(offer_id) if offer_id else f"1688_{abs(hash(source_url))}",
        "code": "",
        "origin": "1688",
        "brand_name": None,
        "name": title,
        "description": description,
        "price": price,
        "shop_name": shop_name,
        "shop_name_chinese": ((shop_name or "").strip()[:200] or None),
        "chinese_name": ((title or "").strip()[:500] or None),
        "shop_id": shop_id,
        "pro_lower_price": lower,
        "pro_high_price": higher,
        "group_rating": 888,
        "group_question": 0,
        "sizes": merged_sizes,
        "colors": colors_out,
        "images": main_ordered,
        "gallery": gallery_sorted,
        "carousel_images_1688": carousel_only_for_export,
        "color_swatch_images_1688": swatches_for_export,
        "detail_block_images_1688": detail_block_only,
        "link_default": source_url,
        "video_link": payload.get("video_url") or structured.get("video_url"),
        "main_image": main_image,
        "likes": _eng["likes"],
        "purchases": _eng["purchases"],
        "rating_total": _eng["rating_total"],
        "question_total": _eng["question_total"],
        "rating_point": _eng["rating_point"],
        "available": 500,
        "deposit_require": 1,
        "category": None,
        "subcategory": None,
        "sub_subcategory": None,
        "material": None,
        "style": None,
        "color": (color_names[0] if color_names else None),
        "occasion": None,
        "features": [],
        "weight": None,
        "product_info": product_info,
        "is_active": True,
    }


def _count_detail_candidates(page: Any) -> int:
    """Độ đầy trang chi tiết: cụm mô tả hoặc tổng ibank (trừ 店铺推荐)."""
    try:
        return int(
            page.evaluate(
                """() => {
                  const reco = '.sdmap-dynamic-offer-list, .desc-dynamic-module.offer-list-wapper, .offer-list-wapper';
                  const bankHint = (img) => {
                    const parts = [
                      img.getAttribute('src'),
                      img.getAttribute('data-src'),
                      img.getAttribute('data-lazy-load-src'),
                      img.currentSrc,
                    ].filter(Boolean).map((s) => String(s));
                    return parts.some((s) => s.includes('img/ibank'));
                  };
                  let detailish = 0;
                  document.querySelectorAll('#detail img, img.dynamic-backup-img, img[usemap*="sdmap"]').forEach((img) => {
                    if (!img.closest || !img.closest(reco)) detailish += 1;
                  });
                  let ibank = 0;
                  document.querySelectorAll('img').forEach((img) => {
                    if (img.closest && img.closest(reco)) return;
                    if (bankHint(img)) ibank += 1;
                  });
                  return detailish >= 12 ? detailish : Math.max(detailish, ibank);
                }"""
            )
        )
    except Exception:
        return 0


def _reveal_1688_detail_content(page: Any) -> Tuple[int, int, List[str]]:
    """
    1688 hay lazy-load hoặc ẩn '#detail' tới khi người dùng chọn tab 「详情 / 图文详情」
    hoặc cuộn tới khối mô tả — mô phỏng các thao tác đó trước khi scrape.
    Trả về thêm URL ảnh thấy trong lớp xem ảnh (Ant modal) sau khi click.
    """
    before = _count_detail_candidates(page)

    # 1) Bấm tab / link có chữ chi tiết (Playwright locator)
    _click_labels = ("图文详情", "产品详情", "商品详情", "详情描述", "详情", "说明")
    for label in _click_labels:
        try:
            tab = page.get_by_role("tab", name=label).first
            if tab.count() and tab.is_visible(timeout=800):
                tab.click(timeout=2000)
                page.wait_for_timeout(900)
        except Exception:
            pass
        try:
            lk = page.get_by_text(label, exact=True).first
            if lk.count() and lk.is_visible(timeout=800):
                lk.click(timeout=2000)
                page.wait_for_timeout(900)
        except Exception:
            pass

    # 2) Click bằng JS: phần tử hiển thị có chứa các chữ trên (tránh không match role/tab)
    try:
        page.evaluate(
            """() => {
              const labels = [/图文详情/, /产品详情/, /商品详情/, /详情描述/, /^详情$/];
              const clickable = [];
              document.querySelectorAll('a, button, span, div, li').forEach((el) => {
                const t = (el.innerText || '').trim();
                if (!t || t.length > 48) return;
                if (!el.offsetParent) return;
                for (const re of labels) {
                  if (re.test(t)) {
                    clickable.push(el);
                    break;
                  }
                }
              });
              clickable.slice(0, 3).forEach((el) => {
                try {
                  el.click();
                } catch (e) {}
              });
            }"""
        )
        page.wait_for_timeout(900)
    except Exception:
        pass

    # 3) Anchor #detail / điều hướng nội bộ
    for sel in ('a[href="#detail"]', 'a[href*="#offer-template"]'):
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible(timeout=600):
                loc.click(timeout=1500)
                page.wait_for_timeout(600)
        except Exception:
            pass

    # 4) Cuộn tuần tự để bật observer lazy (ảnh trong mô tả)
    try:
        for _ in range(14):
            page.evaluate(
                """() => {
                  window.scrollBy(0, Math.min(
                    Math.max(window.innerHeight * 0.75, 400),
                    (document.documentElement.scrollHeight || 99999) - window.scrollY - 120
                  ));
                }"""
            )
            page.wait_for_timeout(320)
            if _count_detail_candidates(page) > max(before + 5, 20):
                break
    except Exception:
        pass

    # 5) Scroll thẳng tới khối mô tả nếu đã có
    try:
        page.evaluate(
            """() => {
              const det = document.getElementById('detail')
                || document.querySelector('[id*="offer-template"][id*="detail"]')
                || document.querySelector('.desc-module-wrap, #desc-lazy-loading-container')
                ;
              det?.scrollIntoView({ block: 'start', behavior: 'instant' });
            }"""
        )
        page.wait_for_timeout(800)
    except Exception:
        pass

    # 6) Bấm ảnh trong khối chi tiết để mở xem lớn / modal — 1688 hay lazy URL đủ chỉ sau tương tác
    preview_layer_urls = _click_1688_detail_images_for_preview(page, max_clicks=14)

    page.wait_for_timeout(900)
    after = _count_detail_candidates(page)
    return before, after, preview_layer_urls


def _click_1688_detail_images_for_preview(page: Any, max_clicks: int = 14) -> List[str]:
    """Cuộn tới từng ảnh mô tả, click để bật lightbox/modal (Ant Design / 1688), gom URL từ lớp preview, rồi Escape."""
    reco = ".sdmap-dynamic-offer-list, .desc-dynamic-module.offer-list-wapper, .offer-list-wapper"
    collected: List[str] = []
    for idx in range(max_clicks):
        try:
            opened = page.evaluate(
                """({ idx, reco }) => {
                  const goodSrc = (src) => {
                    if (!src || src.startsWith('data:')) return false;
                    if (!/\\.(jpe?g|png|webp)|img\\/ibank/i.test(src)) return false;
                    return /(alicdn\\.com|alibab|1688\\.com|tbcdn)/i.test(src);
                  };
                  const collectFromRoots = () => {
                    const imgs = [];
                    const seen = new Set();
                    const roots = Array.from(
                      document.querySelectorAll(
                        '#detail, #desc-lazy-loading-container, .desc-module-wrap, [class*="detail-desc"], [class*="offer-detail"], [id^="offer-template"]'
                      )
                    ).filter((n) => n && n.querySelector);
                    roots.forEach((root) => {
                      root.querySelectorAll('img').forEach((img) => {
                        if (img.closest && img.closest(reco)) return;
                        const src =
                          img.currentSrc ||
                          img.getAttribute('src') ||
                          img.getAttribute('data-lazy-load-src') ||
                          img.getAttribute('data-src') ||
                          '';
                        if (!goodSrc(src)) return;
                        const r = img.getBoundingClientRect();
                        const lazy = !!(img.getAttribute('data-lazy-load-src') && img.getAttribute('data-lazy-load-src').includes('ibank'));
                        if (!lazy && (r.width < 40 || r.height < 40)) return;
                        const key = src.split('?')[0];
                        if (seen.has(key)) return;
                        seen.add(key);
                        imgs.push(img);
                      });
                    });
                    return imgs;
                  };
                  /** Một số template 1688 (Ant Image) không dùng #detail — chỉ có .preview-img */
                  const collectAntPreviewImages = () => {
                    const imgs = [];
                    const seen = new Set();
                    document
                      .querySelectorAll('img.ant-image-img.preview-img, img.preview-img[data-lazy-load-src], img.preview-img')
                      .forEach((img) => {
                        if (img.closest && img.closest(reco)) return;
                        const src =
                          img.currentSrc ||
                          img.getAttribute('src') ||
                          img.getAttribute('data-lazy-load-src') ||
                          img.getAttribute('data-src') ||
                          '';
                        if (!goodSrc(src)) return;
                        const r = img.getBoundingClientRect();
                        const lazy = !!(img.getAttribute('data-lazy-load-src') && img.getAttribute('data-lazy-load-src').includes('ibank'));
                        if (!lazy && (r.width < 36 || r.height < 36)) return;
                        const key = src.split('?')[0];
                        if (seen.has(key)) return;
                        seen.add(key);
                        imgs.push(img);
                      });
                    return imgs;
                  };
                  let imgs = collectFromRoots();
                  if (!imgs.length) imgs = collectAntPreviewImages();

                  if (!imgs.length) return false;
                  const pick = imgs[Math.min(idx, imgs.length - 1)];
                  pick.scrollIntoView({ block: 'center', behavior: 'instant' });
                  const wrap =
                    pick.closest('.ant-image') ||
                    pick.closest('a[href]') ||
                    pick.closest('[role="button"]') ||
                    pick.closest('[onclick]') ||
                    pick.closest('.desc-img') ||
                    pick;
                  try {
                    wrap.click();
                  } catch (e) {
                    try {
                      pick.click();
                    } catch (e2) {}
                  }
                  return true;
                }""",
                {"idx": idx, "reco": reco},
            )
            if not opened:
                break
            page.wait_for_timeout(1100)
            try:
                urls = page.evaluate(
                    """() => {
                      const sels = [
                        '.ant-image-preview img',
                        '.ant-image-preview-wrap img',
                        '.ant-image-preview-body img',
                        '.ant-image-preview-operations-wrapper + img',
                        '[class*="image-preview"] img',
                        '[class*="ImagePreview"] img',
                      ];
                      const out = [];
                      const seen = new Set();
                      sels.forEach((sel) => {
                        document.querySelectorAll(sel).forEach((img) => {
                          const s = (img.currentSrc || img.src || img.getAttribute('data-src') || '').trim();
                          if (!s || s.startsWith('data:')) return;
                          if (!/(alicdn|alibab|img\\/ibank|1688)/i.test(s)) return;
                          const k = s.split('?')[0];
                          if (seen.has(k)) return;
                          seen.add(k);
                          out.push(s);
                        });
                      });
                      return out;
                    }"""
                )
                if isinstance(urls, list):
                    collected.extend(str(u).strip() for u in urls if isinstance(u, str) and u.strip())
            except Exception:
                pass
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(400)
        except Exception:
            continue
    return _dedupe([_normalize_image_url(u) for u in collected if u])


def scrape_1688_product(url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    if not settings.IMPORT_1688_ENABLED:
        raise Import1688Error("Import 1688 đang tắt. Bật IMPORT_1688_ENABLED=true trong backend .env.")
    from app.services.import_hibox_scraper import is_hibox_import_url

    if is_hibox_import_url(url or ""):
        raise Import1688Error(
            "Đây là link Hibox (hibox.mn), không phải link 1688 — không có offerId. "
            "Hãy dùng chức năng import link trên admin: URL Hibox được xử lý riêng. "
            "Nếu cần 1688, dán đúng URL detail.1688.com hoặc detail.m.1688.com có /offer/....html hoặc ?offerId=...."
        )
    offer_id = extract_offer_id(url)
    if not offer_id:
        raise Import1688Error(
            "Link 1688 không hợp lệ hoặc thiếu offerId. "
            "Cần URL dạng detail.1688.com/offer/xxxxxxxx.html hoặc ?offerId= (kể cả detail.m.1688.com/page/... ). "
            "Link Hibox (https://hibox.mn/v/...) không dùng offerId. "
            "Nếu bạn đang dán link Hibox: admin thường gọi nhầm instance API cổng cũ (lệch NEXT_PUBLIC_API_BASE_URL / SERVER_PORT) "
            "trong khi FastAPI của bạn chạy cổng khác — xem frontend/.env.local (API_INTERNAL_ORIGIN, NEXT_PUBLIC_API_BASE_URL) và restart Next + backend."
        )

    fetch_url = url
    product_source_url = url
    pc = canonical_1688_offer_pc_url(offer_id)
    if pc:
        fetch_url = pc
        product_source_url = pc

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise Import1688Error(
            "Backend chưa cài Playwright. Chạy pip install -r requirements.txt và playwright install chromium."
        ) from exc

    cookies = _load_cookie_json()
    warnings: List[str] = []
    if not cookies:
        warnings.append("Chưa cấu hình cookie 1688; trang có thể bị chặn hoặc thiếu dữ liệu.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=settings.IMPORT_1688_USER_AGENT,
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
        )
        if cookies:
            context.add_cookies([_normalize_playwright_cookie(c) for c in cookies])
        page = context.new_page()
        detail_dom_richness_before = 0
        detail_dom_richness_after = 0
        preview_layer_urls: List[str] = []
        try:
            page.goto(fetch_url, wait_until="domcontentloaded", timeout=settings.IMPORT_1688_TIMEOUT_MS)
            try:
                page.wait_for_load_state("networkidle", timeout=min(15000, settings.IMPORT_1688_TIMEOUT_MS))
            except PlaywrightTimeoutError:
                warnings.append("Trang 1688 tải chậm; đã lấy dữ liệu hiện có sau timeout networkidle.")
            page.wait_for_timeout(1500)
            detail_dom_richness_before, detail_dom_richness_after, preview_layer_urls = _reveal_1688_detail_content(page)
            try:
                page.evaluate(
                    """() => {
                      const det = document.getElementById('detail');
                      if (det) det.scrollIntoView({ block: 'start', behavior: 'instant' });
                    }"""
                )
                page.wait_for_timeout(600)
            except Exception:
                pass
            payload = page.evaluate(
                """() => {
                  const meta = (name) =>
                    document.querySelector(`meta[name="${name}"],meta[property="${name}"]`)?.content || '';
                  const scripts = Array.from(document.scripts)
                    .map((s) => s.textContent || '')
                    .filter(Boolean);
                  /** 1688 OD: h1 đầu tiên thường là tên shop (#shopNavigation), title SP ở #productTitle */
                  const productTitleH1 =
                    document.querySelector(
                      '#productTitle h1, [data-module="od_title"] h1, .module-od-title .title-content h1'
                    ) || null;
                  const h1Product = (productTitleH1?.innerText || '').trim();
                  const h1Fallback = (document.querySelector('h1')?.innerText || '').trim();
                  const h1 = h1Product || h1Fallback;
                  const titleNodes = Array.from(document.querySelectorAll('[class*=title],[class*=Title]'))
                    .map((el) => el.innerText || '')
                    .filter((t) => t && t.length > 6)
                    .slice(0, 8);

                  function norm(u) {
                    if (!u || typeof u !== 'string') return '';
                    let s = u.trim();
                    if (s.startsWith('//')) s = 'https:' + s;
                    if (s.startsWith('data:')) return '';
                    return s;
                  }
                  function junk(u) {
                    if (!u) return true;
                    const l = u.toLowerCase();
                    if (l.includes('dmtracking')) return true;
                    if (l.includes('gw.alicdn.com/mt/')) return true;
                    const m = l.match(/tps-(\\d+)-(\\d+)\\./);
                    if (m && parseInt(m[1], 10) <= 96 && parseInt(m[2], 10) <= 96) return true;
                    return false;
                  }
                  function good(u) {
                    if (junk(u)) return false;
                    if (!/(alicdn\\.com|1688\\.com)/i.test(u)) return false;
                    return /\\.(jpe?g|png|webp)/i.test(u);
                  }
                  function makeCollector() {
                    const seen = new Set();
                    const arr = [];
                    const push = (u) => {
                      const n = norm(u);
                      if (!good(n) || seen.has(n)) return;
                      seen.add(n);
                      arr.push(n);
                    };
                    return { arr, push };
                  }

                  function skipShopRecommendation(img) {
                    return !!(img && img.closest && img.closest(
                      '.sdmap-dynamic-offer-list, .desc-dynamic-module.offer-list-wapper, .offer-list-wapper'
                    ));
                  }

                  const c1 = makeCollector();
                  [
                    '.detail-gallery-turn img',
                    '[class*="detail-gallery"] img',
                    '[class*="offer-gallery"] img',
                    '[class*="main-file-image"] img',
                    '[class*="vertical-img"] img',
                    '#gallery .od-gallery-list img.preview-img',
                    '#gallery img.ant-image-img.preview-img',
                    '.od-gallery-preview .od-gallery-list img',
                    '.module-od-picture-gallery img.preview-img',
                  ].forEach((sel) => {
                    try {
                      document.querySelectorAll(sel).forEach((img) => {
                        c1.push(img.currentSrc || img.src || img.getAttribute('data-src') || '');
                      });
                    } catch (e) {}
                  });

                  const c2 = makeCollector();
                  [
                    '#detail img',
                    '#offer-template-0 img',
                    '#offer-template-1450686394303 img',
                    '#desc-lazy-loading-container img',
                    '.desc-module-wrap img',
                    '[class*="desc-module"] img',
                    '[class*="offer-detail"] img',
                    '#dt-tab img',
                    '[class*="desc-img"] img',
                    '[class*="detail-content"] img',
                    '[class*="detail-desc"] img',
                    '[class*="mod-detail"] img',
                    '.mod-detail-bd img',
                    'img.dynamic-backup-img',
                    'img[usemap*="sdmap"]',
                    '.ant-image img',
                    'img.ant-image-img.preview-img',
                  ].forEach((sel) => {
                    try {
                      document.querySelectorAll(sel).forEach((img) => {
                        if (skipShopRecommendation(img)) return;
                        c2.push(
                          img.currentSrc ||
                            img.src ||
                            img.getAttribute('data-lazy-load-src') ||
                            img.getAttribute('data-src') ||
                            ''
                        );
                      });
                    } catch (e) {}
                  });

                  try {
                    document.querySelectorAll('img[src*="img/ibank"]').forEach((img) => {
                      if (skipShopRecommendation(img)) return;
                      c2.push(
                        img.currentSrc ||
                          img.src ||
                          img.getAttribute('data-lazy-load-src') ||
                          img.getAttribute('data-src') ||
                          ''
                      );
                    });
                  } catch (e) {}

                  const c3 = makeCollector();
                  ['[class*="sku-item"] img', '[class*="skuItem"] img', '[class*="prop-item"] img'].forEach((sel) => {
                    try {
                      document.querySelectorAll(sel).forEach((img) => {
                        const u = img.currentSrc || img.src || img.getAttribute('data-src') || '';
                        const n = norm(u);
                        if (!good(n)) return;
                        if (u.includes('imgextra') || u.includes('ibank')) c3.push(u);
                      });
                    } catch (e) {}
                  });
                  /** OD: nút màu trong #skuSelection — có ảnh hoặc chỉ text (.textonly) */
                  const colorVariants = [];
                  const seenColorLabel = new Set();
                  try {
                    document.querySelectorAll('#skuSelection .feature-item').forEach((block) => {
                      const labHdr = block.querySelector('.feature-item-label h3, .feature-item-label');
                      const hdrText = ((labHdr && labHdr.innerText) || '').trim();
                      if (!/颜色/.test(hdrText)) return;
                      block.querySelectorAll('.transverse-filter button.sku-filter-button').forEach((btn) => {
                        const nameEl = btn.querySelector('.label-name');
                        let label = ((nameEl && nameEl.innerText) || '').trim().replace(/\\s+/g, ' ');
                        if (!label || label.length > 80) return;
                        if (seenColorLabel.has(label)) return;
                        seenColorLabel.add(label);
                        const imgEl = btn.querySelector('.label-image-wrap img, img.ant-image-img');
                        let imgUrl = '';
                        if (imgEl) {
                          imgUrl = norm(
                            imgEl.currentSrc ||
                              imgEl.getAttribute('src') ||
                              imgEl.getAttribute('data-src') ||
                              ''
                          );
                          if (!good(imgUrl)) imgUrl = '';
                          else c3.push(imgUrl);
                        }
                        colorVariants.push({ label, image_url: imgUrl || null });
                      });
                    });
                  } catch (e) {}

                  let videoUrl =
                    document.querySelector('video source[src]')?.getAttribute('src') ||
                    document.querySelector('video[src]')?.getAttribute('src') ||
                    '';
                  videoUrl = norm(videoUrl);

                  const titleCandidates = [];
                  if (h1Product) titleCandidates.push(h1Product);
                  if (meta('og:title')) titleCandidates.push(meta('og:title'));
                  if (document.title) titleCandidates.push(document.title);

                  const sizeLabels = [];
                  const seenSize = new Set();
                  const pushSize = (raw) => {
                    const t = (raw || '').trim().split(/\\s+/)[0].trim();
                    if (!t || t.length > 12 || seenSize.has(t)) return;
                    seenSize.add(t);
                    sizeLabels.push(t);
                  };
                  /** OD layout: hàng 尺码 — item-label là S/M/L/XL… */
                  document.querySelectorAll('#skuSelection .feature-item').forEach((block) => {
                    const lab = block.querySelector('.feature-item-label h3, .feature-item-label');
                    const labelText = ((lab && lab.innerText) || '').trim();
                    if (!/尺码/.test(labelText)) return;
                    block.querySelectorAll('.expand-view-item span.item-label[title], .expand-view-item .item-label').forEach(
                      (el) => {
                        if (sizeLabels.length >= 48) return;
                        const fromTitle = el.getAttribute && el.getAttribute('title');
                        pushSize(fromTitle || el.innerText || '');
                      }
                    );
                  });
                  /** Giày / SKU dạng số */
                  document.querySelectorAll('button, span, div, a, li').forEach((el) => {
                    if (sizeLabels.length >= 48) return;
                    const cn = ((el.className && el.className.toString()) || '').toLowerCase();
                    const spm = (el.getAttribute('data-spm') || '').toLowerCase();
                    const matchSku =
                      /(sku|size|尺码|规格|offer|sale)/i.test(cn) ||
                      /(sku|size|尺码|规格)/i.test(spm);
                    if (!matchSku) return;
                    const t = ((el.innerText || '').trim().split(/\\s+/)[0] || '').trim();
                    if (!/^[0-9]{2,4}$/.test(t)) return;
                    pushSize(t);
                  });

                  /** Giá mức 1件起批 (ưu tiên hơn ¥ ship / giảm giá khác trong body) */
                  let main_price_cny = null;
                  try {
                    const roots = document.querySelectorAll(
                      '#mainPrice .price-component, .module-od-main-price .price-component, .od-price-container-step .price-component'
                    );
                    roots.forEach((pc) => {
                      if (main_price_cny != null) return;
                      const txt = (pc.innerText || '').replace(/\\s+/g, '');
                      if (!/1件/.test(txt)) return;
                      const cur = pc.querySelectorAll('.price-info span.currency');
                      if (!cur || !cur.length) return;
                      const whole = (cur[0].textContent || '').trim().replace(/[^0-9]/g, '');
                      let frac = '';
                      if (cur.length > 1) {
                        frac = (cur[1].textContent || '').trim();
                        if (frac.startsWith('.')) frac = frac.slice(1);
                        frac = frac.replace(/[^0-9]/g, '');
                      }
                      const joined = frac ? `${whole}.${frac}` : whole;
                      const n = parseFloat(joined);
                      if (!Number.isFinite(n) || n <= 0 || n > 1000000) return;
                      main_price_cny = n;
                    });
                  } catch (e) {}

                  const structured = {
                    carousel_images: c1.arr,
                    detail_images: c2.arr,
                    color_swatch_images: c3.arr,
                    title_candidates: titleCandidates,
                    size_labels: sizeLabels,
                    color_variants: colorVariants,
                    video_url: videoUrl || null,
                    main_price_cny,
                  };

                  return {
                    document_title: document.title || '',
                    meta_title: meta('og:title') || meta('title'),
                    meta_description: meta('description'),
                    h1,
                    title_nodes: titleNodes,
                    body_text: (document.body?.innerText || '').slice(0, 16000),
                    html_sample: document.documentElement.outerHTML.slice(0, 720000),
                    scripts: scripts.slice(0, 120),
                    structured,
                  };
                }"""
            )
            if preview_layer_urls and isinstance(payload, dict):
                structured = payload.get("structured")
                if isinstance(structured, dict):
                    cur = structured.get("detail_images")
                    base_urls = [_normalize_image_url(u) for u in (cur if isinstance(cur, list) else []) if isinstance(u, str)]
                    structured["detail_images"] = _dedupe(base_urls + list(preview_layer_urls))
        finally:
            for _cleanup in (
                lambda: page.close(),
                lambda: context.close(),
                lambda: browser.close(),
            ):
                try:
                    _cleanup()
                except Exception:
                    pass

    if not isinstance(payload, dict):
        raise Import1688Error("Không đọc được payload từ trang 1688.")
    page_text = " ".join(
        str(payload.get(k) or "") for k in ("document_title", "h1", "meta_title", "body_text")
    ).lower()
    if any(token in page_text for token in ("验证码", "captcha", "verify", "安全验证")):
        raise Import1688Error("1688 đang yêu cầu captcha/xác minh. Cập nhật cookie đăng nhập 1688 rồi thử lại.")
    if not payload.get("h1") and not payload.get("meta_title") and "login" in page_text:
        raise Import1688Error("1688 yêu cầu đăng nhập. Cập nhật IMPORT_1688_COOKIE_JSON rồi thử lại.")

    product_data = normalize_1688_payload(product_source_url, offer_id, payload)
    dom_rich = max(detail_dom_richness_before, detail_dom_richness_after)
    gallery_n = len(product_data.get("gallery") or [])
    structured_pre = payload.get("structured") if isinstance(payload.get("structured"), dict) else {}
    detail_raw_n = len(structured_pre.get("detail_images") or [])
    if dom_rich < 12 and gallery_n < 8 and detail_raw_n < 8:
        warnings.append(
            "Không thấy nhiều ảnh trong khối mô tả chi tiết 1688 (thường cần bấm tab「图文详情」/「详情」hoặc trang chỉ lazy-load khi cuộn). Kiểm tra cookie đăng nhập 1688 và thử lại."
        )
    if not product_data.get("images"):
        warnings.append("Không phát hiện được ảnh sản phẩm; có thể cookie hết hạn hoặc layout 1688 thay đổi.")
    if not product_data.get("price"):
        warnings.append("Không phát hiện được giá; admin cần kiểm tra/sửa trước khi đăng.")
    return payload, product_data, warnings
