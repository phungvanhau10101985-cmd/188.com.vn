"""
Scrape trang Vipomall 1688 mirror -> product_data giống luồng import Hibox/1688.

Vipomall là Angular SPA nên cần Playwright để lấy variant, bảng size/giá/tồn,
gallery và ảnh mô tả sau khi bấm "Xem thêm" / "Xem thêm chi tiết".
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.services.alicdn_urls import truncate_alicdn_url_to_first_jpg
from app.services.import_hibox_scraper import (
    normalize_product_import_url,
    supply_product_link_default_for_hibox_slug,
)
from app.services.vipomall_source_stock import build_vipomall_1688_pdp_url
from app.utils.product_synthetic_engagement import synthetic_engagement_counts


class ImportVipomallError(RuntimeError):
    pass


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


def vipomall_canonical_import_url(raw: str) -> str:
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
    return truncate_alicdn_url_to_first_jpg(u)


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
  const seenColor = new Set();
  document.querySelectorAll(".product-type-list .product-type-item, .product-type-list [title]").forEach((el) => {
    const label = normText(el.getAttribute("title") || el.querySelector(".title")?.innerText || el.textContent);
    if (!label || label.length > 160 || seenColor.has(label.toLowerCase())) return;
    const img = el.querySelector("img");
    colors.push({ label, image_url: imgUrl(img) || null });
    seenColor.add(label.toLowerCase());
  });

  const sizeRows = [];
  const sizeSet = new Set();
  const pairSeen = new Set();
  document.querySelectorAll(".product-size-content-item").forEach((row) => {
    const titles = Array.from(row.querySelectorAll(".size [title], [data-toggle='tooltip'][title]"))
      .map((el) => normText(el.getAttribute("title") || el.textContent))
      .filter(Boolean);
    let color = "";
    let size = "";
    if (titles.length >= 2) {
      color = titles[0];
      size = titles[1];
    } else if (titles.length === 1) {
      size = titles[0];
    }
    const visibleSize = normText(row.querySelector(".size span span")?.innerText || "");
    if (!size && visibleSize) size = visibleSize;
    const stockText = normText(row.querySelector(".product")?.innerText || "");
    let stock = null;
    const sm = stockText.match(/(\d[\d.,]*)\s*SP/i);
    if (sm) stock = parseInt(sm[1].replace(/[^\d]/g, ""), 10);
    const priceText = normText(row.querySelector(".main-price")?.innerText || row.querySelector("[appformatcurrency]")?.innerText || "");
    const priceVnd = parseInt(priceText.replace(/[^\d]/g, ""), 10) || null;
    if (size) sizeSet.add(size);
    if (color || size) {
      const key = `${color}###${size}`;
      if (!pairSeen.has(key)) {
        pairSeen.add(key);
        sizeRows.push({ color, size, stock, price_vnd: priceVnd, price_text: priceText });
      }
    }
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

  return {
    page_url: window.location.href,
    title: titleCandidates[0] || "",
    document_title: document.title || "",
    meta_title: meta("title"),
    meta_description: meta("description"),
    meta_image: meta("image"),
    body_text_sample: text.slice(0, 16000),
    colors,
    sizes: Array.from(sizeSet),
    variant_rows: sizeRows,
    gallery_images: gallery,
    detail_images: detailImages,
    info_texts: infoPairs.slice(0, 80),
    price_texts: priceTexts.slice(0, 20),
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


def scrape_vipomall_for_import(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    return run_import_playwright_sync(lambda: _scrape_vipomall_for_import_sync(source_url))


def _scrape_vipomall_for_import_sync(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    norm = normalize_product_import_url((source_url or "").strip())
    offer_id = extract_vipomall_offer_id(norm)
    if not offer_id:
        raise ImportVipomallError("Link Vipomall không hợp lệ. Dạng cần: https://vipomall.vn/san-pham/{offerId}?platform_type=10")
    page_url = build_vipomall_1688_pdp_url(offer_id)

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
        raise ImportVipomallError(f"Lỗi Playwright/Vipomall: {detail}") from exc

    if not isinstance(raw, dict):
        raise ImportVipomallError("Scraper Vipomall trả về dữ liệu không hợp lệ.")

    page_text = " ".join(str(raw.get(k) or "") for k in ("title", "document_title", "body_text_sample")).lower()
    if any(token in page_text for token in _BLOCK_MARKERS):
        raise ImportVipomallError("Vipomall đang chặn/CAPTCHA hoặc không cho tải PDP.")

    product_data = vipomall_row_to_product_data(raw, page_url, offer_id)
    if not product_data.get("colors"):
        warnings.append("Vipomall: chưa thu được variant màu từ .product-type-list.")
    if not product_data.get("sizes"):
        warnings.append("Vipomall: chưa thu được size từ .product-type-list-size.")
    if not product_data.get("gallery"):
        warnings.append("Vipomall: chưa thu được ảnh chi tiết sau Xem thêm/Xem thêm chi tiết.")
    return raw, product_data, warnings


def vipomall_row_to_product_data(row: Dict[str, Any], source_url: str, offer_id: str) -> Dict[str, Any]:
    gallery = _dedupe_urls([str(u) for u in row.get("gallery_images") or []])
    meta_image = _norm_img_url(str(row.get("meta_image") or ""))

    colors_raw = [c for c in row.get("colors") or [] if isinstance(c, dict)]
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
        detail_imgs.append(u)

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

    variant_rows = [r for r in row.get("variant_rows") or [] if isinstance(r, dict)]
    pair_objs: List[Dict[str, str]] = []
    sizes: List[str] = []
    seen_size: set[str] = set()
    prices: List[float] = []
    stocks: List[int] = []
    for r in variant_rows:
        raw_color = _clean_text(r.get("color"), limit=160)
        size = _clean_text(r.get("size"), limit=80)
        color = color_map.get(raw_color, raw_color)
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
    if not sizes:
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
        title = f"1688 {offer_id}"

    info_texts = _clean_vipomall_info_texts(row.get("info_texts") or [])
    variant_context_parts: List[str] = []
    if colors_out:
        variant_context_parts.append(
            "Màu sắc: " + ", ".join([c.get("name", "") for c in colors_out if c.get("name")])
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
        "supply_platform": "1688",
        "supply_product_url": supply_product_link_default_for_hibox_slug(f"abb-{offer_id}"),
        "vipomall_product_url": source_url,
    }
    if swatches:
        variants["color_swatches"] = swatches
    if sizes:
        variants["sizes"] = sizes
    if variant_rows:
        variants["vipomall_rows"] = variant_rows[:300]

    product_info = {
        "product_info": {
            "name_original": title,
            "listing_sku_hint": f"abb-{offer_id}",
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
    cny_for_excel = _estimate_cny_from_vnd(price_vnd)

    return {
        "product_id": f"A{offer_id}",
        "code": "",
        "origin": "1688",
        "brand_name": None,
        "name": title[:500],
        "chinese_name": title[:500] or None,
        "description": desc[:20000],
        "price": float(price_vnd),
        "shop_name": "Vipomall",
        "shop_name_chinese": None,
        "shop_id": offer_id,
        "pro_lower_price": cny_for_excel,
        "pro_high_price": cny_for_excel,
        "group_rating": 0,
        "group_question": 0,
        "sizes": sizes,
        "colors": colors_out,
        "images": gallery,
        "gallery": detail_imgs,
        "carousel_images_1688": gallery,
        "color_swatch_images_1688": [c["img"] for c in colors_out if c.get("img")],
        "detail_block_images_1688": detail_imgs,
        "link_default": supply_product_link_default_for_hibox_slug(f"abb-{offer_id}") or source_url,
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
