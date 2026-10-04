"""
Scrape trang Vipomall 1688 mirror -> product_data giống luồng import 1688 / PandaMall.

Vipomall là Angular SPA nên cần Playwright để lấy variant, bảng size/giá/tồn,
gallery và ảnh mô tả sau khi bấm "Xem thêm" / "Xem thêm chi tiết".
"""
from __future__ import annotations

import html
import json
import logging
import math
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from app.core.config import settings
from app.services.alicdn_urls import is_excluded_detail_content_image, normalize_product_image_url
from app.services.import_source_ids import (
    build_canonical_taobao_product_id,
    extract_abb_offer_digits,
    extract_legacy_mirror_slug,
    extract_taobao_tmall_item_id,
    is_legacy_placeholder_slug,
    normalize_product_import_url,
    parse_t_prefixed_item_id,
    supply_product_link_default_for_item_slug,
)
from app.services.vipomall_source_stock import (
    VIPOMALL_PLATFORM_1688,
    VIPOMALL_PLATFORM_TAOBAO,
    build_vipomall_1688_pdp_url,
    build_vipomall_pdp_url,
    build_vipomall_taobao_pdp_url,
)
from app.utils.product_synthetic_engagement import synthetic_engagement_counts

logger = logging.getLogger(__name__)

_VIPOMALL_DETAIL_API = "https://api-vipo.viettelpost.vn/listing/product/detail"
_COLOR_PROP_RE = re.compile(r"màu|颜色|colour|color", re.I)
_SIZE_PROP_RE = re.compile(r"kích\s*cỡ|kích\s*thước|尺码|尺寸|size", re.I)
_MODEL_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]{2,}$")
_HTML_IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)


class ImportVipomallError(RuntimeError):
    pass


class _VipomallApiUnavailable(RuntimeError):
    """API detail không dùng được. Import không suy giá từ HTML."""


_VIPOMALL_HOST_RE = re.compile(r"^(?:www\.)?vipomall\.vn$", re.I)
_VIPOMALL_PATH_OFFER_RE = re.compile(r"^/san-pham/(\d+)", re.I)
_BLOCK_MARKERS = ("captcha", "cloudflare", "cf-ray", "access denied", "forbidden", "blocked")
_VIPOMALL_IMAGE_HOST_MARKERS = ("viposeller", "viettelidc.com.vn")


def is_vipomall_import_url(raw: str) -> bool:
    return extract_vipomall_offer_id(raw) is not None


def extract_vipomall_offer_id(raw: str) -> Optional[str]:
    norm = normalize_product_import_url((raw or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    if not _VIPOMALL_HOST_RE.fullmatch(p.hostname or ""):
        return None
    m = _VIPOMALL_PATH_OFFER_RE.match(p.path or "")
    if m:
        return m.group(1)
    qs = parse_qs(p.query or "")
    for key in ("offerId", "offerid", "id", "itemId"):
        for val in qs.get(key) or []:
            s = (val or "").strip()
            if s.isdigit():
                return s
    return None


def extract_vipomall_platform_type(raw: str) -> Optional[int]:
    norm = normalize_product_import_url((raw or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    qs = parse_qs(p.query or "")
    for key in ("platform_type", "platformType"):
        for val in qs.get(key) or []:
            s = (val or "").strip()
            if s.isdigit():
                return int(s)
    return None


def extract_vipomall_merchant_id(raw: str) -> str:
    norm = normalize_product_import_url((raw or "").strip())
    if not norm:
        return "101"
    try:
        qs = parse_qs(urlparse(norm).query or "")
    except ValueError:
        return "101"
    for key in ("merchant_id", "merchantId"):
        for val in qs.get(key) or []:
            s = (val or "").strip()
            if s.isdigit():
                return s
    return "101"


def infer_vipomall_platform_type(source_url: str, offer_id: str) -> int:
    explicit = extract_vipomall_platform_type(source_url)
    if explicit in (VIPOMALL_PLATFORM_1688, VIPOMALL_PLATFORM_TAOBAO):
        return explicit
    norm = normalize_product_import_url((source_url or "").strip())
    if parse_t_prefixed_item_id(norm) or extract_taobao_tmall_item_id(norm):
        return VIPOMALL_PLATFORM_TAOBAO
    slug = extract_legacy_mirror_slug(norm)
    if slug and not is_legacy_placeholder_slug(slug) and not extract_abb_offer_digits(slug):
        if re.fullmatch(r"\d+", slug or ""):
            return VIPOMALL_PLATFORM_TAOBAO
    return VIPOMALL_PLATFORM_1688


def resolve_vipomall_import_url(raw: str) -> Tuple[str, int]:
    """
    Chuẩn hoá mọi link Taobao/Tmall/T-id/abb-*/Vipomall → URL Vipomall + platform_type.
    Taobao/Tmall → platform_type=21; 1688 → platform_type=10.
    """
    trimmed = (raw or "").strip()
    tid = parse_t_prefixed_item_id(trimmed)
    if tid:
        return build_vipomall_taobao_pdp_url(tid), VIPOMALL_PLATFORM_TAOBAO

    norm = normalize_product_import_url(trimmed)
    if not norm:
        raise ImportVipomallError("Link Vipomall/Taobao không hợp lệ.")

    if is_vipomall_import_url(norm):
        oid = extract_vipomall_offer_id(norm)
        if not oid:
            raise ImportVipomallError("Không đọc được id sản phẩm từ link Vipomall.")
        pt = infer_vipomall_platform_type(norm, oid)
        return build_vipomall_pdp_url(oid, pt), pt

    tid = extract_taobao_tmall_item_id(norm)
    if tid:
        return build_vipomall_taobao_pdp_url(tid), VIPOMALL_PLATFORM_TAOBAO

    slug = extract_legacy_mirror_slug(norm)
    if slug and not is_legacy_placeholder_slug(slug):
        abb = extract_abb_offer_digits(slug)
        if abb:
            return build_vipomall_1688_pdp_url(abb), VIPOMALL_PLATFORM_1688
        if re.fullmatch(r"\d+", slug):
            return build_vipomall_taobao_pdp_url(slug), VIPOMALL_PLATFORM_TAOBAO

    from app.services.import_1688_scraper import extract_offer_id

    oid1688 = extract_offer_id(norm)
    if oid1688 and oid1688.isdigit():
        return build_vipomall_1688_pdp_url(oid1688), VIPOMALL_PLATFORM_1688

    raise ImportVipomallError(
        "Không quy đổi được sang Vipomall. Cần link Taobao/Tmall, T{id}, abb-*/số, offer 1688, hoặc vipomall.vn/san-pham/{id}."
    )


def vipomall_canonical_import_url(raw: str) -> str:
    try:
        url, _pt = resolve_vipomall_import_url(raw)
        return url
    except ImportVipomallError:
        oid = extract_vipomall_offer_id(raw)
        return build_vipomall_1688_pdp_url(oid or "") or normalize_product_import_url(raw or "")


def _norm_img_url(raw: str) -> str:
    u = (raw or "").strip().strip('"').strip("'")
    if not u:
        return ""
    if u.startswith("//"):
        u = f"https:{u}"
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    if any(marker in u.lower() for marker in _VIPOMALL_IMAGE_HOST_MARKERS):
        return ""
    return normalize_product_image_url(u)


def _dedupe_urls(values: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in values:
        u = _norm_img_url(str(raw or ""))
        if not u:
            continue
        k = u.split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def _parse_vnd_price(raw: Any) -> float:
    s = str(raw or "")
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return 0.0
    try:
        val = int(digits)
    except ValueError:
        return 0.0
    return float(val) if val > 0 else 0.0


def _listing_vnd_per_cny() -> float:
    val = getattr(settings, "LISTING_IMPORT_VND_PER_CNY", None)
    try:
        rate = float(val)
        if math.isfinite(rate) and rate > 0:
            return rate
    except (TypeError, ValueError):
        pass
    return 3600.0


def _estimate_cny_from_vnd(price_vnd: float) -> str:
    if not math.isfinite(price_vnd) or price_vnd <= 0:
        return ""
    cny = price_vnd / _listing_vnd_per_cny()
    return f"{cny:.4f}".rstrip("0").rstrip(".")


def _clean_text(raw: Any, *, limit: int = 500) -> str:
    s = re.sub(r"\s+", " ", str(raw or "").replace("\xa0", " ")).strip()
    return s[:limit]


_VIPOMALL_INFO_NOISE_RE = re.compile(
    r"(trung tâm hỗ trợ|hướng dẫn|ước tính chi phí|chính sách|hàng cấm|giới thiệu|"
    r"điều khoản dịch vụ|quy chế hoạt động|kinh nghiệm vipomall|vipo\s*mall)",
    re.I,
)


def _clean_vipomall_info_texts(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        s = _clean_text(raw, limit=400)
        if not s or _VIPOMALL_INFO_NOISE_RE.search(s):
            continue
        key = s.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


_SCRAPE_JS = r"""() => {
  const normText = (v) => String(v || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const imgUrl = (img) =>
    normText(img?.currentSrc || img?.src || img?.getAttribute?.("data-src") || img?.getAttribute?.("data-original") || "");
  const pushUnique = (arr, seen, raw) => {
    const u = normText(raw);
    if (!/^https?:\/\//i.test(u)) return;
    if (/assets\/images\//i.test(u)) return;
    const k = u.split("?")[0];
    if (seen.has(k)) return;
    seen.add(k);
    arr.push(u);
  };

  const text = document.body?.innerText || "";
  const meta = (name) =>
    document.querySelector(`meta[property="og:${name}"]`)?.getAttribute("content") ||
    document.querySelector(`meta[name="${name}"]`)?.getAttribute("content") ||
    "";

  const titleCandidates = [];
  document.querySelectorAll("h1, .product-name, .product-title, [class*='product'][class*='name'], [class*='product'][class*='title']").forEach((el) => {
    const t = normText(el.innerText || el.textContent);
    if (t && t.length > 5 && t.length < 500) titleCandidates.push(t);
  });
  if (meta("title")) titleCandidates.push(meta("title"));
  if (document.title) titleCandidates.push(document.title);

  const colors = [];
  const swatchColors = [];
  const seenColor = new Set();
  const seenSwatch = new Set();
  const pushColor = (label, imgEl) => {
    const l = normText(label);
    if (!l || l.length > 160 || seenColor.has(l.toLowerCase())) return;
    colors.push({ label: l, image_url: imgUrl(imgEl) || null });
    seenColor.add(l.toLowerCase());
  };
  const pushSwatchColor = (label, imgEl) => {
    const l = normText(label);
    if (!l || l.length > 160 || seenSwatch.has(l.toLowerCase())) return;
    swatchColors.push({ label: l, image_url: imgUrl(imgEl) || null });
    seenSwatch.add(l.toLowerCase());
    pushColor(label, imgEl);
  };
  document.querySelectorAll(".product-type-list .product-type-item").forEach((el) => {
    const label = normText(
      el.getAttribute("title") || el.querySelector(".title span, .title")?.innerText || el.textContent,
    );
    if (!label) return;
    pushSwatchColor(label, el.querySelector("img"));
  });
  document.querySelectorAll(".product-type-list [title]").forEach((el) => {
    if (el.classList?.contains("product-type-item")) return;
    const label = normText(el.getAttribute("title") || el.querySelector(".title span, .title")?.innerText || el.textContent);
    if (!label) return;
    pushColor(label, el.querySelector("img"));
  });

  const sectionHeaderText = (section) =>
    normText(
      section.querySelector(".header .select span, .header .select .csdf, .header .select")?.innerText || "",
    );
  const sectionTotalText = (section) =>
    normText(
      section.querySelector(".header .total-select span, .header .total-select .csdf, .header .total-select")?.innerText ||
        "",
    );
  const isColorSectionHeader = (t) => /màu\s*sắc|颜色|colour|color/i.test(t);
  const isVariantSectionHeader = (t) =>
    /mẫu|phân\s*loại|规格|款式|kiểu|loại hàng|biến\s*thể|variant|model|style/i.test(t) &&
    !isColorSectionHeader(t);
  const isSizeSectionHeader = (t) =>
    /kích\s*cỡ|尺码|size/i.test(t) && !isColorSectionHeader(t) && !isVariantSectionHeader(t);
  const rowVariantLabel = (row) => {
    const titles = Array.from(
      row.querySelectorAll(".size [title], [data-toggle='tooltip'][title], .size-1 [title]"),
    )
      .map((el) => normText(el.getAttribute("title") || el.textContent))
      .filter(Boolean);
    const visible = normText(
      row.querySelector(".size span span, .size-1 span span, .size-1 span, .size-1")?.innerText || "",
    );
    return { titles, visible };
  };
  const rowLooksVariantOnly = (row) => {
    if (!row.querySelector(".size-1, .size-content .size-1")) return false;
    const sizeCells = Array.from(row.querySelectorAll(".size-content .size, .size-content > .size"));
    return sizeCells.length === 0;
  };
  const resolveSectionKind = (section) => {
    const header = sectionHeaderText(section);
    const total = sectionTotalText(section);
    if (isColorSectionHeader(header)) return "color";
    if (isSizeSectionHeader(header)) return "size";
    if (isVariantSectionHeader(header) || /\d+\s*mẫu/i.test(total)) return "variant";
    const rows = Array.from(section.querySelectorAll(".product-size-content-item"));
    if (rows.length && rows.every((row) => rowLooksVariantOnly(row))) return "variant";
    return "unknown";
  };
  const variantLabelKind = (kind) => kind === "color" || kind === "variant";
  const sizeRows = [];
  const sizeSet = new Set();
  const pairSeen = new Set();
  const pushVariantRow = (row, sectionKind) => {
    const { titles, visible } = rowVariantLabel(row);
    let color = "";
    let size = "";
    if (variantLabelKind(sectionKind)) {
      color = titles[0] || visible;
    } else if (sectionKind === "size") {
      if (titles.length >= 2) {
        color = titles[0];
        size = titles[1];
      } else {
        size = titles[0] || visible;
      }
    } else if (titles.length >= 2) {
      color = titles[0];
      size = titles[1];
    } else if (titles.length === 1) {
      if (rowLooksVariantOnly(row)) color = titles[0];
      else size = titles[0];
    } else if (visible) {
      if (rowLooksVariantOnly(row)) color = visible;
      else size = visible;
    }
    const stockText = normText(row.querySelector(".product")?.innerText || "");
    const isOutOfStock = /hết\s*hàng/i.test(stockText);
    let stock = null;
    const sm = stockText.match(/(\d[\d.,]*)\s*SP/i);
    if (sm) stock = parseInt(sm[1].replace(/[^\d]/g, ""), 10);
    const hasAvailableText = /có\s*sẵn/i.test(stockText);
    const inStock = !isOutOfStock && (hasAvailableText || (stock != null && stock > 0));
    const priceText = normText(
      row.querySelector(".main-price")?.innerText || row.querySelector("[appformatcurrency]")?.innerText || "",
    );
    const priceVnd = parseInt(priceText.replace(/[^\d]/g, ""), 10) || null;
    if (!inStock) return;
    if (size && !variantLabelKind(sectionKind) && !rowLooksVariantOnly(row)) sizeSet.add(size);
    if (color || size) {
      const key = `${color}###${size}`;
      if (!pairSeen.has(key)) {
        pairSeen.add(key);
        sizeRows.push({
          color,
          size,
          image_url: imgUrl(row.querySelector("img")) || null,
          stock,
          price_vnd: priceVnd,
          price_text: priceText,
          stock_text: stockText,
          in_stock: true,
        });
      }
    }
  };

  document.querySelectorAll(".product-type-content .product-type-list-size, .product-type-list-size").forEach((section) => {
    const kind = resolveSectionKind(section);
    if (variantLabelKind(kind)) {
      section.querySelectorAll(".product-size-content-item").forEach((row) => {
        const { titles, visible } = rowVariantLabel(row);
        const label = titles[0] || visible;
        if (label) pushColor(label, row.querySelector("img"));
      });
    }
    section.querySelectorAll(".product-size-content-item").forEach((row) => {
      pushVariantRow(row, kind);
    });
  });
  document.querySelectorAll(".product-size-content-item").forEach((row) => {
    if (row.closest(".product-type-list-size")) return;
    pushVariantRow(row, "unknown");
  });

  const gallery = [];
  const seenGallery = new Set();
  document.querySelectorAll(".list-image img, .list-image-content img, [class*='list-image'] img").forEach((img) => {
    const u = imgUrl(img);
    if (/play-circle/i.test(u)) return;
    pushUnique(gallery, seenGallery, u);
  });

  const detailImages = [];
  const seenDetail = new Set();
  const collectDetailImages = () => {
    const allNodes = Array.from(document.querySelectorAll("body *"));
    const nodeText = (el) => normText(el.innerText || el.textContent);
    const title = allNodes.find((el) => nodeText(el) === "Chi tiết sản phẩm");
    if (!title) return;

    const isAfter = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const isBefore = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_PRECEDING);
    const stop = allNodes.find((el) => {
      const t = nodeText(el);
      if (t !== "Thu gọn") return false;
      return isAfter(title, el);
    });
    const similar = allNodes.find((el) => {
      const t = nodeText(el).toLowerCase();
      if (!t || t.length > 80) return false;
      return t.includes("sản phẩm tương tự") && isAfter(title, el);
    });

    document.querySelectorAll("img[src*='alicdn'], img[src*='cbu01'], img[src*='ibank']").forEach((img) => {
      if (!isAfter(title, img)) return;
      if (stop && !isBefore(stop, img)) return;
      if (!stop && similar && !isBefore(similar, img)) return;
      if (img.closest(".list-image, .list-image-content, .product-type-list, .product-type-list-size, .product-size-content")) return;
      const rect = img.getBoundingClientRect();
      const w = rect.width || img.naturalWidth || 0;
      const h = rect.height || img.naturalHeight || 0;
      if (w > 0 && h > 0 && (w < 80 || h < 80)) return;
      const u = imgUrl(img);
      if (/assets\/images\//i.test(u)) return;
      pushUnique(detailImages, seenDetail, u);
    });
  };
  collectDetailImages();

  const infoPairs = [];
  const seenInfo = new Set();
  const infoRoot = Array.from(document.querySelectorAll(".modal.show, [role='dialog'], .more-info, #moreInfoProd, .modal-dialog, body"))
    .find((el) => (el.innerText || "").includes("Chi tiết sản phẩm")) || document.body;
  infoRoot.querySelectorAll("tr, li, .row, [class*='info'], [class*='spec']").forEach((el) => {
    const t = normText(el.innerText || el.textContent);
    if (!t || t.length < 3 || t.length > 400) return;
    if (/Xem thêm|Thu gọn|Thêm giỏ|Mua ngay/i.test(t)) return;
    if (seenInfo.has(t)) return;
    seenInfo.add(t);
    infoPairs.push(t);
  });

  let videoUrl = "";
  document.querySelectorAll("video source[src], video[src]").forEach((el) => {
    if (videoUrl) return;
    videoUrl = normText(el.getAttribute("src") || el.src || "");
  });

  const priceTexts = [];
  document.querySelectorAll(".main-price, [appformatcurrency], [class*='price']").forEach((el) => {
    const t = normText(el.innerText || el.textContent);
    if (/\d/.test(t) && /đ|₫|vnd/i.test(t)) priceTexts.push(t);
  });

  const shopNameCandidates = [];
  const seenShop = new Set();
  const pushShop = (raw) => {
    const t = normText(raw);
    if (!t || t.length < 2 || t.length > 120 || seenShop.has(t.toLowerCase())) return;
    if (/vipomall|trung tâm hỗ trợ|chính sách/i.test(t)) return;
    seenShop.add(t.toLowerCase());
    shopNameCandidates.push(t);
  };
  document.querySelectorAll(".shop-name, .store-name, [class*='shop-name'], [class*='shopName'], [class*='store-name'], a[href*='shop']").forEach((el) => {
    pushShop(el.getAttribute("title") || el.innerText || el.textContent);
  });

  const cnyPriceTexts = [];
  const cnyRe = /(?:¥|￥|CNY|元)\s*([\d.,]+)/gi;
  const scanCny = (raw) => {
    const t = normText(raw);
    if (!t) return;
    let m;
    while ((m = cnyRe.exec(t)) !== null) {
      const val = normText(m[1]).replace(/,/g, "");
      if (val) cnyPriceTexts.push(val);
    }
  };
  document.querySelectorAll(".main-price, [class*='price'], [class*='Price']").forEach((el) => {
    scanCny(el.innerText || el.textContent);
  });
  scanCny(text.slice(0, 8000));

  return {
    page_url: window.location.href,
    title: titleCandidates[0] || "",
    document_title: document.title || "",
    meta_title: meta("title"),
    meta_description: meta("description"),
    meta_image: meta("image"),
    body_text_sample: text.slice(0, 16000),
    colors,
    swatch_colors: swatchColors,
    sizes: Array.from(sizeSet),
    variant_rows: sizeRows,
    gallery_images: gallery,
    detail_images: detailImages,
    info_texts: infoPairs.slice(0, 80),
    price_texts: priceTexts.slice(0, 20),
    shop_name_candidates: shopNameCandidates.slice(0, 12),
    cny_price_texts: cnyPriceTexts.slice(0, 12),
    video_url: videoUrl,
  };
}"""


def _click_text(page: Any, text: str, *, timeout_ms: int = 2500) -> bool:
    loc = page.locator(f"text={text}").first
    try:
        if loc.count() > 0:
            loc.click(timeout=timeout_ms)
            return True
    except Exception:
        pass
    try:
        return bool(page.evaluate(
            """([needle]) => {
              const n = String(needle || "").trim();
              const els = [...document.querySelectorAll("button, span, div, a")];
              const el = els.find((x) => (x.innerText || x.textContent || "").trim() === n);
              if (el) { el.click(); return true; }
              return false;
            }""",
            [text],
        ))
    except Exception:
        return False


def _listing_vnd_for_cny(price_cny: float) -> float:
    from app.services.listing_cny_grid import (
        cny_exchange_multiplier_from_grid,
        estimate_listing_vnd_rounded,
    )

    coef = cny_exchange_multiplier_from_grid(price_cny)
    vnd = estimate_listing_vnd_rounded(price_cny, coef, _listing_vnd_per_cny())
    return float(vnd or 0)


def _format_cny_cell(price_cny: float) -> str:
    if not math.isfinite(price_cny) or price_cny <= 0:
        return ""
    return f"{price_cny:.4f}".rstrip("0").rstrip(".")


def _prop_kind(prop_name: str) -> str:
    name = prop_name or ""
    if _COLOR_PROP_RE.search(name):
        return "color"
    if _SIZE_PROP_RE.search(name):
        return "size"
    return "variant"


def _sku_cny(sku: Dict[str, Any]) -> float:
    try:
        val = float(sku.get("price") or 0)
    except (TypeError, ValueError):
        val = 0.0
    if val > 0:
        return val
    for band in sku.get("price_ranges") or []:
        if not isinstance(band, dict):
            continue
        try:
            band_price = float(band.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if band_price > 0:
            return band_price
    return 0.0


def _sku_in_stock(sku: Dict[str, Any]) -> bool:
    if sku.get("is_active") is False:
        return False
    stock = sku.get("stock")
    if stock is None or stock == "":
        return True
    try:
        return int(stock) > 0
    except (TypeError, ValueError):
        return True


def _sku_prop_values(sku: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for prop in sku.get("sku_prop_list") or []:
        if not isinstance(prop, dict):
            continue
        value = _clean_text(prop.get("value_name") or prop.get("original_value_name"), limit=160)
        if not value:
            continue
        prop_name = _clean_text(prop.get("prop_name") or prop.get("original_prop_name"), limit=80)
        out.append({"kind": _prop_kind(prop_name), "value": value, "prop_name": prop_name})
    return out


def _html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join([line for line in lines if line])[:20000]


def _html_image_urls(raw_html: str) -> List[str]:
    return _dedupe_urls([m for m in _HTML_IMG_SRC_RE.findall(raw_html or "")])


def fetch_vipomall_product_detail(offer_id: str, platform_type: int, merchant_id: str = "101") -> Dict[str, Any]:
    """POST listing/product/detail. Ném _VipomallApiUnavailable khi không lấy được JSON hợp lệ."""
    payload = {
        "product_id": str(offer_id),
        "platform_type": str(int(platform_type)),
        "product_link": None,
        "merchant_id": str(merchant_id or "101"),
    }
    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    req = Request(
        _VIPOMALL_DETAIL_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://vipomall.vn",
            "Referer": "https://vipomall.vn/",
            "User-Agent": ua,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        raise _VipomallApiUnavailable(str(exc)) from exc
    if not isinstance(body, dict) or str(body.get("status") or "") != "01":
        raise _VipomallApiUnavailable(f"status={body.get('status') if isinstance(body, dict) else type(body).__name__}")
    data = body.get("data")
    if not isinstance(data, dict):
        raise _VipomallApiUnavailable("Thiếu data.")
    return data


def vipomall_label_is_model_code(name: str) -> bool:
    """Mã kiểu 2W41-15GBN-AC220V giữ nguyên. Tên màu tiếng Trung không thuộc dạng này."""
    s = (name or "").strip()
    if not s or " " in s:
        return False
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", s):
        return False
    return bool(_MODEL_CODE_RE.fullmatch(s) and re.search(r"\d", s))


def _finalize_vipomall_color_labels(colors_out: List[Dict[str, Any]], pairs: List[Dict[str, Any]]) -> None:
    """Dịch tên màu tiếng Trung. Mã model giữ nguyên. `sku` luôn trùng `name` sau khi dịch."""
    translatable = [
        c
        for c in colors_out
        if isinstance(c, dict) and not vipomall_label_is_model_code(str(c.get("name") or ""))
    ]
    previous = [(c, str(c.get("name") or "")) for c in translatable]
    if translatable:
        try:
            from app.services.variant_color_translate import apply_deepseek_translations_to_color_entries

            apply_deepseek_translations_to_color_entries(translatable)
        except Exception:
            logger.info("Vipomall: bỏ qua dịch tên màu.", exc_info=True)
    renamed: Dict[str, str] = {}
    for entry, old in previous:
        new = str(entry.get("name") or old)
        if old and new and old != new:
            renamed[old] = new
    for entry in colors_out:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        entry["sku"] = name
    for pair in pairs:
        old = str(pair.get("color") or "")
        if old in renamed:
            pair["color"] = renamed[old]


def vipomall_api_detail_to_product_data(
    detail: Dict[str, Any],
    source_url: str,
    offer_id: str,
    *,
    platform_type: int = VIPOMALL_PLATFORM_1688,
) -> Dict[str, Any]:
    """Map JSON product/detail → product_data. Mã model giữ nguyên; tên màu tiếng Trung được dịch."""
    skus = [s for s in (detail.get("product_sku_info_list") or []) if isinstance(s, dict) and _sku_in_stock(s)]
    parsed: List[Dict[str, Any]] = []
    for sku in skus:
        cny = _sku_cny(sku)
        if cny <= 0:
            continue
        props = _sku_prop_values(sku)
        color = ""
        size = ""
        extras: List[str] = []
        for prop in props:
            if prop["kind"] == "color" and not color:
                color = prop["value"]
            elif prop["kind"] == "size" and not size:
                size = prop["value"]
            else:
                extras.append(prop["value"])
        if not color:
            color = " / ".join(extras) if extras else (props[0]["value"] if props else "")
            extras = []
        elif extras:
            color = " / ".join([color, *extras])
        values_for_code = [p["value"] for p in props] or ([color] if color else [])
        sku_code = ""
        if len(values_for_code) == 1:
            sku_code = values_for_code[0]
        else:
            sku_code = str(sku.get("sku_id") or "").strip() or " / ".join(values_for_code)
        img = _norm_img_url(str(sku.get("img_url") or ""))
        sell = _listing_vnd_for_cny(cny)
        if sell <= 0:
            continue
        parsed.append(
            {
                "color": color or sku_code,
                "size": size,
                "img": img,
                "sku_code": (sku_code or str(sku.get("sku_id") or ""))[:100],
                "price_cny": cny,
                "price": sell,
                "stock": sku.get("stock"),
            }
        )

    has_size = any(row["size"] for row in parsed)
    if not has_size:
        for row in parsed:
            row["size"] = ""

    colors_out: List[Dict[str, Any]] = []
    seen_color: set[str] = set()
    sizes: List[str] = []
    seen_size: set[str] = set()
    pairs: List[Dict[str, Any]] = []
    for row in sorted(parsed, key=lambda r: (r["price"], r["color"], r["size"])):
        label = row["color"] or row["sku_code"] or "Mẫu"
        if label.lower() not in seen_color:
            seen_color.add(label.lower())
            same = [r for r in parsed if (r["color"] or r["sku_code"]) == (row["color"] or row["sku_code"])]
            cheapest = min(same, key=lambda r: r["price"])
            colors_out.append(
                {
                    "name": label,
                    "img": cheapest.get("img") or row["img"],
                    "sku": label,
                    "sku_code": cheapest.get("sku_code") or label,
                    "price": cheapest["price"],
                    "price_cny": cheapest["price_cny"],
                }
            )
        if has_size and row["size"] and row["size"].lower() not in seen_size:
            seen_size.add(row["size"].lower())
            sizes.append(row["size"])
        if has_size:
            pairs.append(
                {
                    "color": label,
                    "size": row["size"],
                    "price": row["price"],
                    "price_cny": row["price_cny"],
                    "sku_code": row["sku_code"],
                    "img": row["img"],
                }
            )

    if not parsed:
        band = detail.get("sku_price_ranges") if isinstance(detail.get("sku_price_ranges"), dict) else {}
        try:
            fallback_cny = float((band or {}).get("min_price") or 0)
        except (TypeError, ValueError):
            fallback_cny = 0.0
        if fallback_cny > 0:
            parsed.append(
                {
                    "color": "",
                    "size": "",
                    "img": "",
                    "sku_code": "",
                    "price_cny": fallback_cny,
                    "price": _listing_vnd_for_cny(fallback_cny),
                    "stock": None,
                }
            )

    prices = [float(r["price"]) for r in parsed if float(r["price"]) > 0]
    cnys = [float(r["price_cny"]) for r in parsed if float(r["price_cny"]) > 0]
    price_vnd = min(prices) if prices else 0.0
    cny_low = min(cnys) if cnys else 0.0
    cny_high = max(cnys) if cnys else 0.0
    cheapest = min(parsed, key=lambda r: r["price"]) if parsed else None

    gallery = _dedupe_urls([str(u) for u in (detail.get("main_img_url_list") or [])])
    desc_html = str(detail.get("description") or "")
    detail_imgs = []
    gallery_keys = {u.split("?")[0] for u in gallery}
    for u in _html_image_urls(desc_html):
        if u.split("?")[0] in gallery_keys:
            continue
        if is_excluded_detail_content_image(u):
            continue
        detail_imgs.append(u)

    main_image = ""
    if cheapest and cheapest.get("img"):
        main_image = cheapest["img"]
    elif gallery:
        main_image = gallery[0]
    if not gallery and main_image:
        gallery = [main_image]

    title = _clean_text(detail.get("product_name"), limit=500)
    if not title:
        title = f"{'Taobao' if platform_type == VIPOMALL_PLATFORM_TAOBAO else '1688'} {offer_id}"
    chinese_name = _clean_text(detail.get("original_product_name"), limit=500) or None

    info_lines: List[str] = []
    for attr in detail.get("product_attribute_list") or []:
        if not isinstance(attr, dict):
            continue
        name = _clean_text(attr.get("attribute_name"), limit=80)
        vals = attr.get("attribute_value_list") or []
        if not isinstance(vals, list):
            continue
        joined = ", ".join([_clean_text(v, limit=80) for v in vals if _clean_text(v, limit=80)])
        if not name or not joined or len(joined) > 240:
            continue
        info_lines.append(f"{name}: {joined}")
    desc = _html_to_text(desc_html)
    if info_lines:
        desc = (desc + "\n\n--- Thông số ---\n" if desc else "--- Thông số ---\n") + "\n".join(info_lines[:40])

    is_taobao = platform_type == VIPOMALL_PLATFORM_TAOBAO
    supply_slug = offer_id if is_taobao else f"abb-{offer_id}"
    supply_url = supply_product_link_default_for_item_slug(supply_slug)
    original_url = _clean_text(detail.get("original_product_url"), limit=500)
    product_id = build_canonical_taobao_product_id(offer_id) if is_taobao else f"A{offer_id}"
    origin = "taobao" if is_taobao else "1688"
    supply_platform = "taobao" if is_taobao else "1688"

    _finalize_vipomall_color_labels(colors_out, pairs)

    variant_bits: List[str] = []
    if colors_out:
        variant_bits.append("Màu sắc: " + ", ".join([c["name"] for c in colors_out if c.get("name")]))
    if sizes:
        variant_bits.append("Kích cỡ: " + ", ".join(sizes))
    supplier_specs = "\n".join([*variant_bits, *info_lines[:40]]).strip()

    variants: Dict[str, Any] = {
        "pairs": pairs,
        "source": "vipomall",
        "supply_platform": supply_platform,
        "supply_product_url": supply_url,
        "vipomall_product_url": source_url,
        "vipomall_platform_type": platform_type,
    }
    if colors_out and not sizes:
        variants["variant_only"] = True
    if sizes:
        variants["sizes"] = sizes
    if pairs:
        variants["price_pairs"] = [
            {
                "color": p.get("color") or "",
                "size": p.get("size") or "",
                "price": p.get("price"),
                "price_cny": p.get("price_cny"),
                "sku_code": p.get("sku_code") or "",
            }
            for p in pairs
        ]
    if colors_out:
        variants["color_swatches"] = [{"label": c["name"], "image_url": c.get("img") or None} for c in colors_out]

    video = ""
    for key in ("main_video", "detail_video"):
        cand = _clean_text(detail.get(key), limit=1000)
        if cand.startswith("http"):
            video = cand
            break
    if not video:
        for item in detail.get("main_video_url_list") or []:
            cand = _clean_text(item, limit=1000)
            if cand.startswith("http"):
                video = cand
                break

    stocks: List[int] = []
    for row in parsed:
        try:
            stock_n = int(row.get("stock") or 0)
        except (TypeError, ValueError):
            stock_n = 0
        if stock_n > 0:
            stocks.append(stock_n)

    shop_name = _clean_text(detail.get("shop_name"), limit=200) or "Vipomall"
    shop_cn = _clean_text(detail.get("original_shop_name"), limit=200) or None
    eng = synthetic_engagement_counts()
    cny_low_cell = _format_cny_cell(cny_low)
    cny_high_cell = _format_cny_cell(cny_high)

    return {
        "product_id": product_id,
        "code": "",
        "origin": origin,
        "brand_name": None,
        "name": title[:500],
        "chinese_name": chinese_name,
        "description": desc[:20000],
        "price": float(price_vnd),
        "cost_cny": float(cny_low) if cny_low > 0 else None,
        "shop_name": shop_name,
        "shop_name_chinese": shop_cn,
        "shop_id": offer_id,
        "pro_lower_price": cny_low_cell,
        "pro_high_price": cny_high_cell or cny_low_cell,
        "group_rating": 888,
        "group_question": 0,
        "sizes": sizes,
        "colors": colors_out,
        "images": gallery,
        "gallery": detail_imgs,
        "carousel_images_1688": gallery,
        "color_swatch_images_1688": [c["img"] for c in colors_out if c.get("img")],
        "detail_block_images_1688": detail_imgs,
        "link_default": original_url or supply_url or source_url,
        "video_link": video,
        "main_image": main_image,
        "likes": eng["likes"],
        "purchases": eng["purchases"],
        "rating_total": eng["rating_total"],
        "question_total": eng["question_total"],
        "rating_point": eng["rating_point"],
        "available": max(stocks) if stocks else 500,
        "deposit_require": 1,
        "category": None,
        "subcategory": None,
        "sub_subcategory": None,
        "material": None,
        "style": None,
        "color": ", ".join([c.get("name", "") for c in colors_out if c.get("name")])[:500] or None,
        "occasion": None,
        "features": [],
        "weight": None,
        "product_info": {
            "product_info": {"name_original": title, "listing_sku_hint": product_id},
            "market_info": {
                "currency": "VND",
                "price_cny_low": cny_low or None,
                "price_cny_high": cny_high or None,
                "listing_import_vnd_per_cny_used": _listing_vnd_per_cny(),
            },
            "specifications": {
                "supplier_specs_excerpt": supplier_specs[:4000],
                "vipomall_info_texts": info_lines[:40],
            },
            "variants": variants,
        },
        "is_active": True,
        "slug": "",
    }


def _scrape_vipomall_via_api(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    try:
        page_url, platform_type = resolve_vipomall_import_url(source_url)
    except ImportVipomallError:
        norm = normalize_product_import_url((source_url or "").strip())
        offer_id = extract_vipomall_offer_id(norm)
        if not offer_id:
            raise ImportVipomallError(
                "Link Vipomall không hợp lệ. Dạng: https://vipomall.vn/san-pham/{id}?platform_type=10|21"
            )
        platform_type = infer_vipomall_platform_type(norm, offer_id)
        page_url = build_vipomall_pdp_url(offer_id, platform_type)
    offer_id = extract_vipomall_offer_id(page_url) or ""
    if not offer_id:
        raise ImportVipomallError("Không đọc được id sản phẩm từ link Vipomall.")
    merchant_id = extract_vipomall_merchant_id(source_url)
    detail = fetch_vipomall_product_detail(offer_id, platform_type, merchant_id)
    product_data = vipomall_api_detail_to_product_data(
        detail, page_url, offer_id, platform_type=platform_type
    )
    warnings: List[str] = []
    if not product_data.get("colors") and not product_data.get("price"):
        raise _VipomallApiUnavailable("API không có SKU và không có giá.")
    if not product_data.get("colors"):
        warnings.append("Vipomall API: không có SKU còn hàng — chỉ lấy giá sản phẩm.")
    raw = {
        "source": "vipomall_api",
        "page_url": page_url,
        "offer_id": offer_id,
        "platform_type": platform_type,
        "sku_count": len(product_data.get("colors") or []),
        "title": product_data.get("name") or "",
    }
    return raw, product_data, warnings


def scrape_vipomall_for_import(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    try:
        return _scrape_vipomall_via_api(source_url)
    except ImportVipomallError:
        raise
    except Exception as exc:
        logger.info("Vipomall API detail không dùng được (%s). Không suy giá từ HTML.", exc)
        raise ImportVipomallError(
            "Không lấy được giá tệ từng mã từ Vipomall. Thử lại."
        ) from exc


def _scrape_vipomall_for_import_sync(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    try:
        page_url, platform_type = resolve_vipomall_import_url(source_url)
    except ImportVipomallError:
        norm = normalize_product_import_url((source_url or "").strip())
        offer_id = extract_vipomall_offer_id(norm)
        if not offer_id:
            raise ImportVipomallError(
                "Link Vipomall không hợp lệ. Dạng: https://vipomall.vn/san-pham/{id}?platform_type=10|21"
            )
        platform_type = infer_vipomall_platform_type(norm, offer_id)
        page_url = build_vipomall_pdp_url(offer_id, platform_type)
    offer_id = extract_vipomall_offer_id(page_url) or ""

    warnings: List[str] = []
    raw: Dict[str, Any] = {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportVipomallError("Thiếu Playwright để scrape Vipomall.") from exc

    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    headless_raw = getattr(settings, "SOURCE_STOCK_CHECK_HEADLESS", True)
    headless = str(headless_raw).strip().lower() not in {"0", "false", "no"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                viewport={"width": 1366, "height": 1000},
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                user_agent=ua,
            )
            page = context.new_page()
            try:
                from app.services.import_scraper_cookies import seed_playwright_context_cookies

                seed_playwright_context_cookies(
                    context,
                    page,
                    prefer_hosts={"vipomall.vn"},
                    target_url=page_url,
                )
            except Exception:
                pass
            try:
                page.goto(page_url, wait_until="domcontentloaded", timeout=90_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=35_000)
                except Exception:
                    pass
                page.wait_for_timeout(2500)
                for y in (500, 1200, 2200, 3600):
                    page.evaluate("([yy]) => window.scrollTo(0, yy)", [y])
                    page.wait_for_timeout(650)
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(600)

                _click_text(page, "Xem thêm")
                page.wait_for_timeout(1200)
                _click_text(page, "Xem thêm chi tiết")
                page.wait_for_timeout(1500)
                for y in (800, 1800, 3200, 5200, 7600):
                    page.evaluate("([yy]) => window.scrollTo(0, yy)", [y])
                    page.wait_for_timeout(600)
                try:
                    page.locator(".modal.show, [role='dialog']").first.evaluate(
                        """(el) => { try { el.scrollTop = el.scrollHeight; } catch (_) {} }"""
                    )
                    page.wait_for_timeout(700)
                except Exception:
                    pass
                raw = page.evaluate(_SCRAPE_JS)
            finally:
                for cleanup in (page.close, context.close, browser.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
    except Exception as exc:
        detail = str(exc).strip() or repr(exc) or type(exc).__name__
        if "Executable doesn't exist" in detail or "playwright install" in detail.lower():
            detail = (
                f"{detail} — Trên server (Linux): "
                "cd backend && source .venv/bin/activate && python -m playwright install chromium "
                "(hoặc: bash deploy/install-playwright-browsers.sh từ root repo)."
            )
        raise ImportVipomallError(f"Lỗi Playwright/Vipomall: {detail}") from exc

    if not isinstance(raw, dict):
        raise ImportVipomallError("Scraper Vipomall trả về dữ liệu không hợp lệ.")

    page_text = " ".join(str(raw.get(k) or "") for k in ("title", "document_title", "body_text_sample")).lower()
    if any(token in page_text for token in _BLOCK_MARKERS):
        raise ImportVipomallError("Vipomall đang chặn/CAPTCHA hoặc không cho tải PDP.")

    product_data = vipomall_row_to_product_data(raw, page_url, offer_id, platform_type=platform_type)
    if not product_data.get("colors"):
        warnings.append("Vipomall: chưa thu được variant màu từ .product-type-list / .product-type-list-size.")
    if not product_data.get("sizes") and not product_data.get("colors"):
        raw_variant_count = len([r for r in (raw.get("variant_rows") or []) if isinstance(r, dict)])
        if raw_variant_count:
            warnings.append(
                "Vipomall: mọi size đều hết hàng — đã bỏ biến thể «Hết hàng», không còn size nào import."
            )
        else:
            warnings.append("Vipomall: chưa thu được size từ .product-type-list-size.")
    if not product_data.get("gallery"):
        warnings.append("Vipomall: chưa thu được ảnh chi tiết sau Xem thêm/Xem thêm chi tiết.")
    return raw, product_data, warnings


def _pick_shop_name_chinese(row: Dict[str, Any]) -> Optional[str]:
    for raw in row.get("shop_name_candidates") or []:
        s = _clean_text(raw, limit=200)
        if s and re.search(r"[\u4e00-\u9fff]", s):
            return s[:200]
    body = str(row.get("body_text_sample") or "")
    for m in re.finditer(r"([\u4e00-\u9fff]{2,40}(?:旗舰店|专卖店|店))", body):
        cand = m.group(1).strip()
        if len(cand) >= 4:
            return cand[:200]
    return None


def _pick_cny_price(row: Dict[str, Any], price_vnd: float) -> str:
    for raw in row.get("cny_price_texts") or []:
        s = str(raw or "").strip().replace(",", "")
        if not s:
            continue
        try:
            val = float(s)
        except ValueError:
            continue
        if 0 < val < 9_999_999:
            return f"{val:.4f}".rstrip("0").rstrip(".")
    for t in row.get("price_texts") or []:
        m = re.search(r"(?:¥|￥|CNY|元)\s*([\d.,]+)", str(t))
        if m:
            s = m.group(1).replace(",", "")
            try:
                val = float(s)
            except ValueError:
                continue
            if 0 < val < 9_999_999:
                return f"{val:.4f}".rstrip("0").rstrip(".")
    return _estimate_cny_from_vnd(price_vnd)


def _is_vipomall_variant_in_stock(r: Dict[str, Any]) -> bool:
    """Chỉ giữ biến thể còn hàng — bỏ dòng «(Hết hàng)» trên Vipomall."""
    if r.get("in_stock") is False:
        return False
    stock_text = _clean_text(r.get("stock_text") or "", limit=160)
    if re.search(r"hết\s*hàng", stock_text, re.I):
        return False
    if r.get("in_stock") is True:
        return True
    try:
        stock = int(r.get("stock") or 0)
    except (TypeError, ValueError):
        stock = 0
    if stock > 0:
        return True
    if re.search(r"có\s*sẵn", stock_text, re.I):
        return True
    return False


def _vipomall_variant_rows_are_color_only(variant_rows: List[Dict[str, Any]]) -> bool:
    return bool(variant_rows) and all(not _clean_text(r.get("size"), limit=80) for r in variant_rows)


def _vipomall_append_color_entry(
    *,
    label: str,
    image_url: str,
    colors_raw: List[Dict[str, Any]],
    colors_out: List[Dict[str, str]],
    swatches: List[Dict[str, Optional[str]]],
    seen: set[str],
) -> None:
    name = _clean_text(label, limit=160)
    if not name:
        return
    key = name.casefold()
    if key in seen:
        return
    seen.add(key)
    img = _norm_img_url(image_url)
    colors_raw.append({"label": name, "image_url": img or None})
    colors_out.append({"name": name, "img": img})
    swatches.append({"label": name, "image_url": img or None})


def _vipomall_remap_variant_only_rows(
    colors_raw: List[Dict[str, Any]],
    colors_out: List[Dict[str, str]],
    swatches: List[Dict[str, Optional[str]]],
    variant_rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[Dict[str, Optional[str]]], List[Dict[str, Any]]]:
    """
    Section «Mẫu» / chỉ variant (.size-1, không size): JS đôi khi gán nhãn vào `size`.
    Chuyển về `color` và bổ sung `colors[]` + ảnh từ từng dòng.
    """
    if colors_out:
        return colors_raw, colors_out, swatches, variant_rows

    remapped_rows: List[Dict[str, Any]] = []
    new_colors_raw = list(colors_raw)
    new_colors_out = list(colors_out)
    new_swatches = list(swatches)
    seen = {_clean_text(c.get("name"), limit=160).casefold() for c in new_colors_out if c.get("name")}

    has_color_field = any(_clean_text(r.get("color"), limit=160) for r in variant_rows)
    if has_color_field:
        for r in variant_rows:
            label = _clean_text(r.get("color"), limit=160)
            img = _norm_img_url(str(r.get("image_url") or ""))
            if label:
                _vipomall_append_color_entry(
                    label=label,
                    image_url=img,
                    colors_raw=new_colors_raw,
                    colors_out=new_colors_out,
                    swatches=new_swatches,
                    seen=seen,
                )
            remapped_rows.append(r)
        return new_colors_raw, new_colors_out, new_swatches, remapped_rows

    for r in variant_rows:
        label = _clean_text(r.get("size"), limit=160)
        if not label:
            remapped_rows.append(r)
            continue
        nr = dict(r)
        nr["color"] = label
        nr["size"] = ""
        remapped_rows.append(nr)
        img = _norm_img_url(str(r.get("image_url") or ""))
        _vipomall_append_color_entry(
            label=label,
            image_url=img,
            colors_raw=new_colors_raw,
            colors_out=new_colors_out,
            swatches=new_swatches,
            seen=seen,
        )

    if new_colors_out:
        return new_colors_raw, new_colors_out, new_swatches, remapped_rows
    return colors_raw, colors_out, swatches, variant_rows


def vipomall_row_to_product_data(
    row: Dict[str, Any],
    source_url: str,
    offer_id: str,
    *,
    platform_type: int = VIPOMALL_PLATFORM_1688,
) -> Dict[str, Any]:
    gallery = _dedupe_urls([str(u) for u in row.get("gallery_images") or []])
    meta_image = _norm_img_url(str(row.get("meta_image") or ""))

    swatch_colors_raw = [c for c in row.get("swatch_colors") or [] if isinstance(c, dict)]
    colors_raw = swatch_colors_raw or [c for c in row.get("colors") or [] if isinstance(c, dict)]
    preserve_all_swatch_colors = bool(swatch_colors_raw)
    colors_out: List[Dict[str, str]] = []
    swatches: List[Dict[str, Optional[str]]] = []
    for idx, c in enumerate(colors_raw):
        label = _clean_text(c.get("label"), limit=160) or f"Màu {idx + 1}"
        img = _norm_img_url(str(c.get("image_url") or ""))
        colors_out.append({"name": label, "img": img})
        swatches.append({"label": label, "image_url": img or None})

    exclude_detail_keys = {u.split("?")[0] for u in gallery if u}
    exclude_detail_keys.update(c["img"].split("?")[0] for c in colors_out if c.get("img"))
    detail_imgs = []
    for u in _dedupe_urls([str(x) for x in row.get("detail_images") or []]):
        if u.split("?")[0] in exclude_detail_keys:
            continue
        if is_excluded_detail_content_image(u):
            continue
        detail_imgs.append(u)

    variant_rows = [
        r for r in row.get("variant_rows") or [] if isinstance(r, dict) and _is_vipomall_variant_in_stock(r)
    ]
    colors_raw, colors_out, swatches, variant_rows = _vipomall_remap_variant_only_rows(
        colors_raw, colors_out, swatches, variant_rows
    )
    exclude_detail_keys.update(c["img"].split("?")[0] for c in colors_out if c.get("img"))

    try:
        from app.services.variant_color_translate import apply_deepseek_translations_to_color_entries

        apply_deepseek_translations_to_color_entries(colors_out)
    except Exception:
        pass

    color_map: Dict[str, str] = {}
    for raw_c, out_c in zip(colors_raw, colors_out):
        raw_label = _clean_text(raw_c.get("label"), limit=160)
        vn_label = _clean_text(out_c.get("name"), limit=160)
        if raw_label and vn_label:
            color_map[raw_label] = vn_label
    for i, sw in enumerate(swatches):
        if i < len(colors_out):
            sw["label"] = _clean_text(colors_out[i].get("name"), limit=160) or sw.get("label")

    pair_objs: List[Dict[str, str]] = []
    sizes: List[str] = []
    seen_size: set[str] = set()
    prices: List[float] = []
    stocks: List[int] = []
    in_stock_raw_colors: set[str] = set()
    for r in variant_rows:
        raw_color = _clean_text(r.get("color"), limit=160)
        size = _clean_text(r.get("size"), limit=80)
        color = color_map.get(raw_color, raw_color)
        if raw_color:
            in_stock_raw_colors.add(raw_color)
        if color and size:
            pair_objs.append({"color": color, "size": size})
        if size and size.lower() not in seen_size:
            seen_size.add(size.lower())
            sizes.append(size)
        price_vnd = _parse_vnd_price(r.get("price_vnd") or r.get("price_text"))
        if price_vnd > 0:
            prices.append(price_vnd)
        try:
            stock = int(r.get("stock") or 0)
        except (TypeError, ValueError):
            stock = 0
        if stock > 0:
            stocks.append(stock)
    raw_color_labels = {
        _clean_text(c.get("label"), limit=160)
        for c in colors_raw
        if _clean_text(c.get("label"), limit=160)
    }
    variant_color_labels = {
        _clean_text(r.get("color"), limit=160)
        for r in variant_rows
        if _clean_text(r.get("color"), limit=160)
    }
    has_extra_swatch_colors = bool(raw_color_labels - variant_color_labels)
    if in_stock_raw_colors and not preserve_all_swatch_colors and not has_extra_swatch_colors:
        colors_out = [
            c
            for c, raw_c in zip(colors_out, colors_raw)
            if _clean_text(raw_c.get("label"), limit=160) in in_stock_raw_colors
        ]
        swatches = [
            sw
            for sw, raw_c in zip(swatches, colors_raw)
            if _clean_text(raw_c.get("label"), limit=160) in in_stock_raw_colors
        ]

    # Layout chỉ variant (túi, phụ kiện, SP nhiều mẫu «3 Mẫu»…): không có size → sizes=[].
    variant_only_layout = _vipomall_variant_rows_are_color_only(variant_rows)
    color_only_layout = bool(colors_out) and variant_only_layout
    if color_only_layout:
        sizes = []
        for r in variant_rows:
            raw_color = _clean_text(r.get("color"), limit=160)
            color = color_map.get(raw_color, raw_color)
            if color:
                pair_objs.append({"color": color, "size": ""})
    elif not sizes:
        sizes = [_clean_text(s, limit=80) for s in row.get("sizes") or [] if _clean_text(s, limit=80)]

    price_vnd = min(prices) if prices else 0.0
    if price_vnd <= 0:
        for t in row.get("price_texts") or []:
            price_vnd = _parse_vnd_price(t)
            if price_vnd > 0:
                break
    main_image = (gallery[0] if gallery else "") or (colors_out[0]["img"] if colors_out else "")
    if not gallery and main_image:
        gallery = [main_image]

    title = _clean_text(row.get("title") or row.get("meta_title") or row.get("document_title"), limit=500)
    if "vipomall" in title.lower() and "-" in title:
        title = title.split("-", 1)[0].strip() or title
    if not title:
        title = f"{'Taobao' if platform_type == VIPOMALL_PLATFORM_TAOBAO else '1688'} {offer_id}"

    shop_cn = _pick_shop_name_chinese(row)
    is_taobao = platform_type == VIPOMALL_PLATFORM_TAOBAO
    supply_slug = offer_id if is_taobao else f"abb-{offer_id}"
    supply_url = supply_product_link_default_for_item_slug(supply_slug)
    product_id = build_canonical_taobao_product_id(offer_id) if is_taobao else f"A{offer_id}"
    origin = "taobao" if is_taobao else "1688"
    supply_platform = "taobao" if is_taobao else "1688"
    cny_for_excel = _pick_cny_price(row, price_vnd)

    info_texts = _clean_vipomall_info_texts(row.get("info_texts") or [])
    variant_context_parts: List[str] = []
    if colors_out:
        label = "Biến thể" if color_only_layout else "Màu sắc"
        variant_context_parts.append(
            f"{label}: " + ", ".join([c.get("name", "") for c in colors_out if c.get("name")])
        )
    if sizes:
        variant_context_parts.append("Kích cỡ: " + ", ".join(sizes))
    if pair_objs:
        variant_context_parts.append(
            "Biến thể màu-size: "
            + "; ".join([f"{p.get('color')} / {p.get('size')}" for p in pair_objs[:80]])
        )
    supplier_specs_excerpt = "\n".join([*variant_context_parts, *info_texts[:80]]).strip()
    desc = _clean_text(row.get("meta_description"), limit=2000)
    if info_texts:
        desc = (desc + "\n\n--- Thông số ---\n" if desc else "--- Thông số ---\n") + "\n".join(info_texts[:60])

    variants: Dict[str, Any] = {
        "pairs": pair_objs,
        "source": "vipomall",
        "supply_platform": supply_platform,
        "supply_product_url": supply_url,
        "vipomall_product_url": source_url,
        "vipomall_platform_type": platform_type,
    }
    if color_only_layout:
        variants["variant_only"] = True
    if swatches:
        variants["color_swatches"] = swatches
    if sizes:
        variants["sizes"] = sizes
    if variant_rows:
        variants["vipomall_rows"] = variant_rows[:300]

    product_info = {
        "product_info": {
            "name_original": title,
            "listing_sku_hint": product_id,
        },
        "market_info": {
            "currency": "VND",
            "vipomall_price_vnd": price_vnd or None,
            "price_cny_approx": float(_estimate_cny_from_vnd(price_vnd) or 0) or None,
            "listing_import_vnd_per_cny_used": _listing_vnd_per_cny(),
        },
        "specifications": {
            "supplier_specs_excerpt": supplier_specs_excerpt[:4000],
            "vipomall_info_texts": info_texts[:80],
        },
        "variants": variants,
    }
    eng = synthetic_engagement_counts()

    return {
        "product_id": product_id,
        "code": "",
        "origin": origin,
        "brand_name": None,
        "name": title[:500],
        "chinese_name": title[:500] or None,
        "description": desc[:20000],
        "price": float(price_vnd),
        "shop_name": "Vipomall",
        "shop_name_chinese": shop_cn,
        "shop_id": offer_id,
        "pro_lower_price": cny_for_excel,
        "pro_high_price": cny_for_excel,
        "group_rating": 888,
        "group_question": 0,
        "sizes": sizes,
        "colors": colors_out,
        "images": gallery,
        "gallery": detail_imgs,
        "carousel_images_1688": gallery,
        "color_swatch_images_1688": [c["img"] for c in colors_out if c.get("img")],
        "detail_block_images_1688": detail_imgs,
        "link_default": supply_url or source_url,
        "video_link": _clean_text(row.get("video_url"), limit=1000),
        "main_image": main_image,
        "likes": eng["likes"],
        "purchases": eng["purchases"],
        "rating_total": eng["rating_total"],
        "question_total": eng["question_total"],
        "rating_point": eng["rating_point"],
        "available": max(stocks) if stocks else 500,
        "deposit_require": 1,
        "category": None,
        "subcategory": None,
        "sub_subcategory": None,
        "material": None,
        "style": None,
        "color": ", ".join([c.get("name", "") for c in colors_out if c.get("name")])[:500] or None,
        "occasion": None,
        "features": [],
        "weight": None,
        "product_info": product_info,
        "is_active": True,
        "slug": "",
    }
