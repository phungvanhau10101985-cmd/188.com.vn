"""
Chuyển trang chi tiết hibox.mn (Nuxt SPA) → product_data thống nhất với import 1688 / export Excel draft.
Không cookie; Playwright được gọi qua scripts/export_hibox_item_excel.py.

Giá (`price`, VNĐ): giá hiển thị trang Hibox là ₮ (số nối chữ số) → chia `HIBOX_MNT_PER_CNY_FOR_LISTING`
(~CN¥) × hệ số lưới IF (`listing_cny_grid`) × `LISTING_IMPORT_VND_PER_CNY`, làm tròn lên 10.000 ₫
(khớp batch Excel listing / `taobao-cards-html-parse.ts`).

Định danh URL …/v/<slug>:
  • slug «abb-<chữ số>» (vd abb-922386436529) → nguồn **1688** → `link_default` = detail.1688.com/offer/<số>.html, origin «1688», product_id **A<số>**.
  • slug khác (vd chỉ số 797317200783) → **Taobao/Tmall** → `link_default` = detail.tmall.com/item.htm?id=… (cùng kiểu với Taobao), origin «taobao», product_id **T<id>**.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

from app.core.config import settings
from app.services.alicdn_urls import normalize_product_image_url
from app.services.listing_cny_grid import (
    DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE,
    cny_exchange_multiplier_from_grid,
    estimate_listing_vnd_rounded,
)
from app.utils.product_synthetic_engagement import synthetic_engagement_counts


_STRIP_INVISIBLE_PREFIX = re.compile(r"^[\ufeff\u200b\u200c\u200d\u2060\s]+")

# Hibox trong câu / markdown; optional locale /xx/ trước /v/
_HIBOX_ABS_V_RE = re.compile(
    r"(?i)\bhttps?://(?:[a-z0-9][a-z0-9.-]*\.)*hibox\.mn(?::\d+)?(?:/[a-z]{2,5})?/v/([^\s/?#\"'<>()\]]+)",
)
# domain bare: hibox.mn/v/… hoặc hibox.mn/en/v/…
_BARE_HIBOX_V_RE = re.compile(
    r"(?i)\b(?:www\.)?(?:[a-z0-9][a-z0-9.-]*\.)*hibox\.mn(?::\d+)?(?:/[a-z]{2,5})?/v/([^\s/?#\"'<>()\]]+)",
)
# Mirror: taobao1688.kz/item?id=<mã> — cùng mã với hibox.mn/v/<mã>
_TAOBAO1688_KZ_HOST_RE = re.compile(r"^(?:www\.)?taobao1688\.kz$", re.I)
_MIRROR_ITEM_ID_RE = re.compile(r"^[a-zA-Z0-9][\w.-]{1,220}$")
# Ghép product_id khi publish: T{id} — id lấy sau /v/ hoặc ?id= mirror
_CANONICAL_HIBOX_PRODUCT_ITEM_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,220}$")
_T_PREFIX_ITEM_RE = re.compile(r"^[Tt](\d{5,})$")
_TAOBAO_TMAIL_HOST_RE = re.compile(r"(?:^|\.)taobao\.com$|(?:^|\.)tmall\.com$", re.I)

# Modal một màu kiểu «Зургийн өнгө» — đồng bộ với export_hibox_item_excel (chuẩn catalogue).
_HIBOX_PIC_COLOR_RE = re.compile(
    r"picture\s*color|图\s*片\s*色|图色|如图所示|按图片|同色|as\s+shown",
    re.I,
)

# …/v/abb-<offerId_1688> — cửa hàng 1688 trên Hibox (không phải Taobao).
_HIBOX_SLUG_1688_ABB_RE = re.compile(r"(?i)^abb-(\d+)$")


def _hibox_catalog_color_label(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return s
    if "Зургийн" in s and "өнгө" in s:
        return "Màu như ảnh"
    if _HIBOX_PIC_COLOR_RE.search(s):
        return "Màu như ảnh"
    return s


def parse_t_prefixed_item_id(raw: str) -> Optional[str]:
    """Mã nội bộ T801751959231 → 801751959231."""
    s = (raw or "").strip()
    m = _T_PREFIX_ITEM_RE.match(s)
    return m.group(1) if m else None


def extract_taobao_tmall_item_id(url: str) -> Optional[str]:
    """Trích id SP từ URL taobao.com / tmall.com (?id= / item_id)."""
    norm = normalize_product_import_url((url or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    host = (p.hostname or "").lower().replace("www.", "")
    if not _TAOBAO_TMAIL_HOST_RE.search(host):
        return None
    qs = parse_qs(p.query or "")
    for key in ("id", "item_id", "itemId"):
        for val in qs.get(key) or []:
            s = (val or "").strip()
            if s.isdigit():
                return s
    return None


def extract_hibox_1688_offer_digits(slug: str) -> Optional[str]:
    """«abb-922386436529» → «922386436529»; slug khác → None."""
    m = _HIBOX_SLUG_1688_ABB_RE.match((slug or "").strip())
    return m.group(1) if m else None


def hibox_slug_is_1688_offer(slug: str) -> bool:
    return extract_hibox_1688_offer_digits(slug) is not None


def _hibox_join_visible_text_snippets(raw_row: Mapping[str, Any]) -> str:
    specs = raw_row.get("specs_text")
    specs_s = specs if isinstance(specs, str) else ""
    if len(specs_s) > 20000:
        specs_s = specs_s[:20000]
    blobs: List[str] = []
    for k in ("title", "h1", "description"):
        v = raw_row.get(k)
        if isinstance(v, str) and v.strip():
            blobs.append(v.strip())
    bt = raw_row.get("body_text_sample")
    if isinstance(bt, str) and bt.strip():
        blobs.append(bt.strip()[:14000])
    if specs_s.strip():
        blobs.append(specs_s.strip())
    return unicodedata.normalize("NFKC", "\n".join(blobs))


def _hibox_casefold_hyphen_relaxed(s: str) -> str:
    out = unicodedata.normalize("NFKC", s)
    for sep in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"):
        out = out.replace(sep, "-")
    return out.casefold()


def hibox_scrape_signals_removed_or_not_found_offer(raw_row: Mapping[str, Any]) -> bool:
    """
    PDP Hibox (Playwright) vẫn có title/slug kỹ thuật nhưng là trang báo không có offer / đã xóa Taobao 1688 —
    coi là hết hàng (ưu tiên logic kiểm tra nguồn).
    Khớp nhiều ngôn ngữ (Mông Cổ Kirin, tiếng Trung, một mẫu EN).
    """
    joined = _hibox_join_visible_text_snippets(raw_row).strip()
    if not joined:
        return False
    hay_relaxed = _hibox_casefold_hyphen_relaxed(joined)

    raw_markers = (
        # Mongolian Cyrillic — Hibox (cả chữ HOA như trên trang lỗi)
        "ИЙМ КОДТОЙ БАРАА ОЛДСОНГҮЙ!",
        "ИЙМ КОДТОЙ БАРАА ОЛДСОНГҮЙ",
        "Ийм кодтой бараа олдсонгүй",
        "олдсонгүй",
        "олсонгүй",
        "Taobao-с устсан",
        # Gợi ý SP tương tự sau khi offer biến mất (cả câu, tránh báo sai trên PDP thường).
        "Ижил төстэй барааг танд санал болгож байна",
        # Chinese
        "商品不存在",
        "找不到商品",
        "页面失效",
        "已下架",
        "商品已经下架",
        # English-ish
        "removed from taobao",
        "no longer exists on taobao",
    )
    for m in raw_markers:
        lm = _hibox_casefold_hyphen_relaxed(m).strip()
        if lm and lm in hay_relaxed:
            return True

    # Taobao + «đã xóa» (Mông Cổ Kirin «устсан») trong cùng nội dung
    if "taobao" in hay_relaxed and "устсан" in hay_relaxed:
        return True

    return False


def supply_product_link_default_for_hibox_slug(slug: str) -> str:
    """
    URL chi tiết NCC cho cột link_default / product_url (không dùng URL trang Hibox).
    abb-<digits> → 1688 detail; còn lại → Taobao/Tmall (cùng kiểu item.htm?id=…).
    """
    oid = extract_hibox_1688_offer_digits(slug)
    if oid:
        return f"https://detail.1688.com/offer/{oid}.html"
    tid = (slug or "").strip()
    if not tid:
        return ""
    # Taobao & Tmall dùng cùng dạng path/query id (skuId có thể bổ sung sau).
    return f"https://detail.tmall.com/item.htm?id={quote(tid, safe='')}"


def build_canonical_hibox_product_id(item_id: str, sku_code: str = "") -> str:
    """
    Mã nội bộ **Taobao** qua Hibox: T + id item (slug sau /v/, không phải dạng abb-*).
    Ví dụ …/v/797317200783 → T797317200783.

    Slug dạng abb-<số> (1688 trên Hibox) → dùng build_canonical_product_id_from_hibox_slug.
    """
    tid = str(item_id or "").strip()
    if not tid:
        raise ValueError("thiếu mã item Hibox/Taobao (đoạn sau /v/).")
    if not _CANONICAL_HIBOX_PRODUCT_ITEM_RE.fullmatch(tid):
        raise ValueError(f"mã item Hibox/Taobao không hợp lệ: {tid!r}")
    return f"T{tid}"


def build_canonical_product_id_from_hibox_slug(slug: str, sku_code: str = "") -> str:
    """
    Ghép product_id khi publish draft nguồn Hibox:
    - abb-<digits> → A<digits> (1688)
    - còn lại (vd chỉ số) → T<slug> (Taobao)
    """
    hid = (slug or "").strip()
    oid = extract_hibox_1688_offer_digits(hid)
    if oid:
        if not oid.isdigit():
            raise ValueError("offer id 1688 (sau abb-) phải là chữ số.")
        return f"A{oid}"
    return build_canonical_hibox_product_id(hid)


def canonicalize_hibox_placeholder_product_id(product_data: Dict[str, Any]) -> None:
    """
    Draft scrape đặt product_id = «hibox_<slug>» (vd hibox_abb-922386436529).
    Đổi thành A<id1688> hoặc T<id> giống luồng publish — không đổi nếu không phải
    prefix hibox_ hoặc thiếu slug hợp lệ.
    """
    pid = (product_data.get("product_id") or "").strip()
    if not pid.startswith("hibox_"):
        return
    slug = pid[len("hibox_") :].strip()
    if not slug or slug.lower() == "hibox_import":
        return
    try:
        product_data["product_id"] = build_canonical_product_id_from_hibox_slug(slug)
    except ValueError:
        pass


class ImportHiboxError(RuntimeError):
    pass


def _taobao1688_kz_hostname_ok(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    return bool(_TAOBAO1688_KZ_HOST_RE.fullmatch(str(hostname).strip().lower()))


def extract_taobao1688_kz_item_id(url: str) -> Optional[str]:
    """
    https://taobao1688.kz/item?id=abb-922386436529#... → abb-922386436529
    (cùng định danh trang chi tiết Hibox).
    """
    norm = normalize_product_import_url((url or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    if not _taobao1688_kz_hostname_ok(p.hostname):
        return None
    qs = parse_qs(p.query)
    for key in ("id", "item_id", "itemId"):
        for v in qs.get(key) or []:
            raw = (v or "").strip()
            if raw and _MIRROR_ITEM_ID_RE.match(raw):
                return raw
    return None




def normalize_product_import_url(raw: str) -> str:
    """Chuẩn hoá URL dán từ ô input: câu có kèm URL, markdown, thiếu https, v.v."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _STRIP_INVISIBLE_PREFIX.sub("", s)
    s = re.sub(r"[\ufeff\u200b-\u200d\u2060]", "", s)
    if not s.strip():
        return ""
    s = s.strip()

    # Markdown / câu chứa URL — lấy URL http(s) đầu tiên (tránh `https://Toàn câu...`)
    m_http = re.search(r"\bhttps?://[^\s\]\)<>\'\"]+", s, flags=re.I)
    if m_http:
        s = m_http.group(0).rstrip(".,;:\"'”’)]}")
    else:
        # Chỉ có dạng domain .../v/... không scheme
        m_bare = _BARE_HIBOX_V_RE.search(s)
        if m_bare:
            start = m_bare.start()
            frag = s[start : m_bare.end()]
            if not frag.lower().startswith(("http://", "https://")):
                s = f"https://{frag.lstrip('/')}"
            else:
                s = frag

    s = s.strip().strip('"').strip("'").strip("\u201c").strip("\u201d").strip(">").strip("<")
    if s.lower().startswith("//"):
        return f"https:{s}"
    if not re.match(r"^[a-z][a-z0-9+.-]*:", s, re.I):
        return f"https://{s.lstrip('/')}"
    return s


def _hibox_hostname_ok(hostname: Optional[str]) -> bool:
    """Chỉ *.hibox.mn thật — tránh evilhibox.mn (endswith '.hibox.mn' nhưng không phải subdomain)."""
    if not hostname:
        return False
    h = str(hostname).lower().rstrip(".")
    return bool(re.fullmatch(r"(?:[\w-]+\.)*hibox\.mn", h))


def _slug_from_hibox_path(path: str) -> Optional[str]:
    """`/v/slug`, `/locale/v/slug`, hoặc `/v/cat/slug` — lấy segment sau `/v/` cuối cùng."""
    if not path:
        return None
    low = path.lower()
    i = low.rfind("/v/")
    if i < 0:
        return None
    rest = path[i + len("/v/") :].strip("/")
    if not rest:
        return None
    slug = rest.split("/")[-1].strip()
    return slug or None


def extract_hibox_slug(url: str) -> Optional[str]:
    raw = normalize_product_import_url((url or "").strip())
    if not raw:
        return None

    parsed = urlparse(raw)
    if _hibox_hostname_ok(parsed.hostname):
        slug = _slug_from_hibox_path(parsed.path or "")
        if slug:
            return slug

    m = _HIBOX_ABS_V_RE.search(raw)
    if m:
        seg = (m.group(1) or "").strip("/").strip()
        if seg:
            return seg.split("/")[-1].strip()

    kz = extract_taobao1688_kz_item_id(raw)
    if kz:
        return kz

    return None


def is_hibox_import_url(raw: str) -> bool:
    """
    URL thuộc host Hibox (*.hibox.mn) hoặc mirror taobao1688.kz?...id=<mã> (cùng mã với hibox.mn/v/<mã>).
    """
    norm = normalize_product_import_url(raw or "")
    if not norm:
        return False
    try:
        p = urlparse(norm)
    except ValueError:
        return False
    if _hibox_hostname_ok(p.hostname):
        return True
    return extract_taobao1688_kz_item_id(norm) is not None


def hibox_canonical_scrape_url(url: str) -> str:
    """URL mà Playwright mở: luôn hibox.mn/v/{slug} khi đã trích được slug."""
    norm = normalize_product_import_url(url.strip())
    slug = extract_hibox_slug(norm)
    if slug and slug != "hibox_import":
        return f"https://hibox.mn/v/{slug}"
    return norm


def _normalize_image_url(url: str) -> str:
    u = (url or "").strip().strip('"').strip("'")
    if not u:
        return ""
    return normalize_product_image_url(u)


def _load_hibox_scrape_module():  # noqa: ANN401
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "export_hibox_item_excel.py"
    if not path.exists():
        raise ImportHiboxError(f"Không thấy script scraper Hibox: {path}")
    spec = importlib.util.spec_from_file_location("hibox_export_script", path)
    if spec is None or spec.loader is None:
        raise ImportHiboxError("Không load được module scrape Hibox.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jlist(row: Dict[str, Any], key: str) -> List[str]:
    raw = row.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    s = str(raw).strip()
    if not s:
        return []
    try:
        out = json.loads(s)
        if isinstance(out, list):
            return [str(x).strip() for x in out if str(x).strip()]
    except Exception:
        pass
    return []


def _color_variant_labels_list(row: Dict[str, Any]) -> List[str]:
    """Song song `color_variant_images_json`; giữ phần tử rỗng để khớp index."""
    raw_l = row.get("color_variant_labels_json")
    if raw_l is None:
        return []
    if isinstance(raw_l, list):
        return ["" if x is None else str(x) for x in raw_l]
    s = str(raw_l).strip()
    if not s:
        return []
    try:
        jl = json.loads(s)
        if isinstance(jl, list):
            return ["" if x is None else str(x) for x in jl]
    except Exception:
        pass
    return []


def _ag_color_column_from_colors_out(colors_out: List[Dict[str, str]]) -> Optional[str]:
    """Cột Excel Color (AG): các màu đã dịch/ghi trong biến thể, cách nhau bởi dấu phẩy."""
    parts: List[str] = []
    seen_l: set[str] = set()
    for it in colors_out:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name") or "").strip()
        if not n:
            continue
        k = n.lower()
        if k in seen_l:
            continue
        seen_l.add(k)
        parts.append(n)
    return ", ".join(parts) if parts else None


def _parse_display_price_integer(s: Any) -> float:
    """Giá hiển thị kiểu 78.900 ₮ hay 78,900 — lấy số nguyên (bỏ dấu ngăn nghìn)."""
    t = str(s or "")
    if not re.search(r"\d", t):
        return 0.0
    digits = "".join(ch for ch in t if ch.isdigit())
    if not digits:
        return 0.0
    try:
        return float(min(int(digits), 9_999_999_999))
    except ValueError:
        return 0.0


def _hibox_mnt_per_cny_for_listing() -> float:
    """Khớp `DEFAULT_MNT_PER_CNY_FOR_HIBOX_LISTING` trên frontend (`taobao-cards-html-parse.ts`)."""
    raw = getattr(settings, "HIBOX_MNT_PER_CNY_FOR_LISTING", None)
    try:
        x = float(raw) if raw is not None else 475.0
    except (TypeError, ValueError):
        x = 475.0
    return x if math.isfinite(x) and x > 0 else 475.0


def _listing_import_vnd_per_cny() -> float:
    raw = getattr(settings, "LISTING_IMPORT_VND_PER_CNY", None)
    try:
        x = float(raw) if raw is not None else DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE
    except (TypeError, ValueError):
        x = DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE
    return x if math.isfinite(x) and x > 0 else DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE


def _hibox_price_vnd_from_display_mnt(mnt_display: float) -> tuple[float, float]:
    """
    ₮ (UI) → ~CN¥ × hệ_số_IF × tỷ giá → VNĐ (float, đã làm tròn lên bội 10k).
    Trả (price_vnd, cny_approx).
    """
    if not math.isfinite(mnt_display) or mnt_display <= 0:
        return 0.0, 0.0
    mnt_per = _hibox_mnt_per_cny_for_listing()
    if not math.isfinite(mnt_per) or mnt_per <= 0:
        return 0.0, 0.0
    cny_approx = float(mnt_display) / float(mnt_per)
    if not math.isfinite(cny_approx) or cny_approx <= 0:
        return 0.0, 0.0
    coef = cny_exchange_multiplier_from_grid(cny_approx)
    vnd_rate = _listing_import_vnd_per_cny()
    vnd_i = estimate_listing_vnd_rounded(cny_approx, coef, vnd_rate)
    if vnd_i is None or vnd_i <= 0:
        return 0.0, cny_approx
    return float(vnd_i), cny_approx


def hibox_row_to_product_data(row: Dict[str, Any], source_url: str, slug: str) -> Dict[str, Any]:
    """Map một dòng scrape (export_hibox_item_excel) → dict giống normalize_1688_payload."""
    gallery = [_normalize_image_url(u) for u in _jlist(row, "gallery_images_json") if u]
    desc_imgs = [_normalize_image_url(u) for u in _jlist(row, "description_images_json") if u]
    color_sw = [_normalize_image_url(u) for u in _jlist(row, "color_variant_images_json") if u]
    specs_imgs = [_normalize_image_url(u) for u in _jlist(row, "specs_images_json") if u]

    colors = _jlist(row, "colors_json")
    labels_th = _color_variant_labels_list(row)
    sizes = _jlist(row, "sizes_json")

    title = (row.get("title") or row.get("h1") or "").strip() or slug
    shop_cn_hint = (
        str(row.get("shop_name_chinese") or row.get("supplier_shop_cn") or row.get("store_name_cn") or "")
        .strip()[:250]
    )
    desc_short = (row.get("description") or "").strip()
    specs_text = (row.get("specs_text") or "").strip()
    if specs_text and len(specs_text) > 80:
        desc_block = f"{desc_short}\n\n--- Thông số ---\n{specs_text[:12000]}".strip()
    else:
        desc_block = desc_short

    # Link slug chỉ dùng làm hint nguồn, không ghi vào cột `sku`.
    scraped_page_sku = (row.get("supplier_sku_scraped") or "").strip()
    if not scraped_page_sku:
        scraped_page_sku = (row.get("sku") or "").strip()
    link_slug = (slug or "").strip()
    mnt_display = _parse_display_price_integer(row.get("price_listed")) or _parse_display_price_integer(
        row.get("price_estimate"),
    )
    price_vnd, cny_approx = _hibox_price_vnd_from_display_mnt(mnt_display)
    cny_for_excel = ""
    if cny_approx > 0:
        cny_for_excel = f"{cny_approx:.4f}".rstrip("0").rstrip(".")

    video_link = (row.get("video_url") or "").strip()

    main_image = _normalize_image_url(str(row.get("og_image") or "")) or (gallery[0] if gallery else "")

    detail_gallery: List[str] = []
    seen_d: set[str] = set()
    for u in desc_imgs + specs_imgs:
        k = u.split("?")[0]
        if not u or k in seen_d:
            continue
        seen_d.add(k)
        detail_gallery.append(u)

    pair_objs: List[Dict[str, str]] = []
    try:
        plist = json.loads(row.get("variant_color_size_json") or "[]")
        if isinstance(plist, list):
            for it in plist:
                if isinstance(it, dict) and it.get("color") and it.get("size"):
                    pair_objs.append({"color": str(it["color"]), "size": str(it["size"])})
    except Exception:
        pair_objs = []

    # Ảnh thumbnail từng màu (ӨНГӨ) → cùng cấu trúc web `ProductColor`: `name` + `img`.
    swatch_pairs: List[Dict[str, Optional[str]]] = []
    if color_sw:
        for i, img in enumerate(color_sw):
            lab = None
            if i < len(labels_th) and (labels_th[i] or "").strip():
                lab = labels_th[i].strip()
            elif i < len(colors):
                lab = str(colors[i]).strip() if colors[i] else None
            swatch_pairs.append({"label": lab, "image_url": img})
    elif colors:
        for c in colors:
            swatch_pairs.append({"label": c, "image_url": None})

    colors_out: List[Dict[str, str]] = []
    if swatch_pairs:
        for i, sp in enumerate(swatch_pairs):
            raw_lab = sp.get("label")
            if raw_lab is not None and str(raw_lab).strip():
                lab_s = str(raw_lab).strip()
            else:
                lab_s = f"Màu {i + 1}"
            img_u = (sp.get("image_url") or "").strip()
            colors_out.append({"name": lab_s, "img": img_u})
    elif colors:
        for c in colors:
            if c is None or str(c).strip() == "":
                continue
            lab_s = str(c).strip()
            colors_out.append({"name": lab_s, "img": ""})

    pic_thumb = main_image or (gallery[0] if gallery else "")
    # Giữ nhãn gốc NCC theo từng ô swatch để map sang `pairs` (variant_color_size_json) sau khi dịch màu.
    supplier_color_labels: List[str] = [
        str(co.get("name") or "").strip() for co in colors_out
    ]
    for co in colors_out:
        nm = str(co.get("name") or "").strip()
        cat = _hibox_catalog_color_label(nm)
        if cat == "Màu như ảnh":
            co["name"] = "Màu như ảnh"
            if not str(co.get("img") or "").strip() and pic_thumb:
                co["img"] = pic_thumb

    variants: Dict[str, Any] = {"pairs": pair_objs, "source": "hibox"}
    supply_plat = "1688" if hibox_slug_is_1688_offer(slug) else "taobao"
    supply_link = supply_product_link_default_for_hibox_slug(slug)
    variants["supply_platform"] = supply_plat
    if supply_link:
        variants["supply_product_url"] = supply_link
    if swatch_pairs:
        variants["color_swatches"] = swatch_pairs
    if sizes:
        variants["sizes"] = sizes

    product_info = {
        "product_info": {
            "name_original": title,
            "sku_ui": row.get("code_ui") or "",
            "listing_sku_hint": scraped_page_sku or None,
        },
        "market_info": {
            "currency": "VND",
            "hibox_display_mnt_integer": int(mnt_display) if mnt_display else None,
            "hibox_mnt_per_cny_used": _hibox_mnt_per_cny_for_listing(),
            "price_cny_approx": round(cny_approx, 6) if cny_approx > 0 else None,
            "listing_import_vnd_per_cny_used": _listing_import_vnd_per_cny(),
        },
        "specifications": {"supplier_specs_excerpt": specs_text[:4000] if specs_text else ""},
        "variants": variants,
        "hibox_supplier_color_labels": supplier_color_labels,
    }

    _eng = synthetic_engagement_counts()

    out: Dict[str, Any] = {
        "product_id": build_canonical_product_id_from_hibox_slug(link_slug) if link_slug else "hibox_import",
        "code": "",
        "origin": supply_plat,
        "brand_name": None,
        "name": title[:500],
        "chinese_name": (title or "")[:500] or None,
        "description": desc_block[:20000],
        "price": float(price_vnd),
        "shop_name": "Hibox",
        "shop_name_chinese": shop_cn_hint or None,
        "shop_id": slug,
        "pro_lower_price": cny_for_excel,
        "pro_high_price": cny_for_excel,
        "group_rating": 0,
        "group_question": 0,
        "sizes": sizes,
        "colors": colors_out,
        "images": gallery,
        "gallery": detail_gallery,
        "carousel_images_1688": gallery,
        "color_swatch_images_1688": color_sw,
        "detail_block_images_1688": [_normalize_image_url(u) for u in desc_imgs],
        "link_default": supply_link or source_url,
        "video_link": video_link,
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
        "color": _ag_color_column_from_colors_out(colors_out) or (str(colors[0]).strip() if colors else None),
        "occasion": None,
        "features": [],
        "weight": None,
        "product_info": product_info,
        "is_active": True,
        "slug": "",
    }

    return out


def _hibox_sync_variant_display_labels(product_data: Dict[str, Any]) -> None:
    """
    Sau khi DeepSeek dịch `colors[]`: map pairs theo nhãn NCC gốc, đồng bộ swatch + cột color / variants.colors.
    """
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return
    supplier_labels = pi.get("hibox_supplier_color_labels")
    if not isinstance(supplier_labels, list):
        supplier_labels = []
    colors_out = product_data.get("colors") or []
    if not isinstance(colors_out, list):
        return

    sup_to_display: Dict[str, str] = {}
    for sup, co in zip(supplier_labels, colors_out):
        if not isinstance(co, dict):
            continue
        sup_s = str(sup or "").strip()
        vn = str(co.get("name") or "").strip()
        if sup_s and vn:
            sup_to_display[sup_s] = vn

    variants = pi.get("variants")
    if not isinstance(variants, dict):
        return
    for po in variants.get("pairs") or []:
        if not isinstance(po, dict):
            continue
        cr = str(po.get("color") or "").strip()
        if cr and cr in sup_to_display:
            po["color"] = sup_to_display[cr]
    sw_list = variants.get("color_swatches") or []
    for i, sp in enumerate(sw_list):
        if i < len(colors_out) and isinstance(sp, dict) and isinstance(colors_out[i], dict):
            lab = str(colors_out[i].get("name") or "").strip()
            if lab:
                sp["label"] = lab
    flat_color = _ag_color_column_from_colors_out(
        [c for c in colors_out if isinstance(c, dict)]
    )
    if flat_color:
        product_data["color"] = flat_color
        variants["colors"] = flat_color


def _slug_from_path_after_any_v(norm: str) -> Optional[str]:
    """Khi urlparse hostname lệch: segment sau /locale/v/ hoặc /v/ trên URL đã normalize."""
    cleaned = (norm or "").replace("\\", "/")
    for pat in (
        r"(?i)/(?:[a-z0-9_-]{1,14}/)?v/([^/?#\s\"'<>]+)",
        r"(?i)/v/([^/?#\s\"'<>]+)",
    ):
        m = re.search(pat, cleaned)
        if m:
            seg = (m.group(1) or "").strip("/").strip()
            tail = seg.split("/")[-1].strip()
            return tail or None
    return None


def scrape_hibox_for_import(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    norm_url = normalize_product_import_url(source_url.strip())
    slug = extract_hibox_slug(norm_url) or _slug_from_path_after_any_v(norm_url)
    if not slug and is_hibox_import_url(norm_url):
        slug = "hibox_import"
    if not slug:
        raise ImportHiboxError(
            "Link Hibox / mirror taobao1688.kz không hợp lệ hoặc không đọc được mã trong URL. "
            "Dạng thường gặp: https://hibox.mn/v/{mã} hoặc https://taobao1688.kz/item?id={mã}"
        )

    warnings: List[str] = []
    scrape_url = hibox_canonical_scrape_url(norm_url)
    if scrape_url.rstrip("/") != norm_url.rstrip("/"):
        warnings.append(f"Link mirror / khác host → Playwright mở: {scrape_url}")
    try:
        mod = _load_hibox_scrape_module()
        scrape_fn = getattr(mod, "scrape_hibox_item", None)
        if callable(scrape_fn) is False:
            raise ImportHiboxError("Script Hibox thiếu hàm scrape_hibox_item.")
        raw_row = scrape_fn(scrape_url)
    except ImportHiboxError:
        raise
    except Exception as exc:
        raise ImportHiboxError(f"Lỗi Playwright/Hibox: {exc}") from exc

    if not isinstance(raw_row, dict):
        raise ImportHiboxError("Scraper Hibox trả về dữ liệu không hợp lệ.")

    if not (raw_row.get("sku") or raw_row.get("title")):
        warnings.append("Hibox: thiếu SKU/title — kiểm tra lại URL hoặc trạng thái trang.")

    cv = raw_row.get("color_variant_image_count") or len(_jlist(raw_row, "color_variant_images_json"))
    if not cv:
        warnings.append(
            "Hibox: chưa thu được ảnh mẫu màu (ӨНГӨ); thử đăng nhập/cookie không cần, hoặc bấm mở sheet chọn variant trước khi export.",
        )

    product_data = hibox_row_to_product_data(raw_row, norm_url, slug)
    try:
        from app.services.variant_color_translate import apply_hibox_variant_color_translation

        warnings.extend(apply_hibox_variant_color_translation(product_data))
        _hibox_sync_variant_display_labels(product_data)
    except Exception as exc:
        warnings.append(f"Hibox: lỗi đồng bộ dịch màu — {type(exc).__name__}: {exc}")

    if hibox_slug_is_1688_offer(slug):
        warnings.append(
            "Hibox: slug abb-* là nguồn cửa hàng 1688 — khi đăng dùng product_id A<số offer>."
        )
    return dict(raw_row), product_data, warnings
