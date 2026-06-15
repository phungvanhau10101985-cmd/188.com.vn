"""
Scrape trang PandaMall (gương Taobao / 1688) → product_data thống nhất với import Hibox/Vipomall.

URL:
  • https://pandamall.vn/taobao/detail/{itemId}
  • https://pandamall.vn/1688/detail/{offerId}
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.core.config import settings
from app.services.alicdn_urls import normalize_product_image_url
from app.services.import_1688_scraper import canonical_1688_offer_pc_url, extract_offer_id
from app.services.import_hibox_scraper import (
    build_canonical_hibox_product_id,
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    extract_taobao_tmall_item_id,
    normalize_product_import_url,
    parse_t_prefixed_item_id,
    supply_product_link_default_for_hibox_slug,
)
from app.utils.product_synthetic_engagement import synthetic_engagement_counts

PANDAMALL_PLATFORM_TAOBAO = "taobao"
PANDAMALL_PLATFORM_1688 = "1688"

_PANDAMALL_HOST_RE = re.compile(r"^(?:www\.)?pandamall\.vn$", re.I)
_PANDAMALL_DETAIL_RE = re.compile(r"^/(taobao|1688)/detail/(\d+)", re.I)
_BLOCK_MARKERS = ("captcha", "cloudflare", "cf-ray", "access denied", "forbidden", "blocked")
_PANDAMALL_INFO_NOISE_RE = re.compile(
    r"(quy trình order|đăng ký tài khoản|liên hệ chúng tôi|pandamall\.vn\s*$)",
    re.I,
)


class ImportPandamallError(RuntimeError):
    pass


def is_pandamall_import_url(raw: str) -> bool:
    return extract_pandamall_detail(raw) is not None


def extract_pandamall_detail(raw: str) -> Optional[Tuple[str, str]]:
    """Trả (item_id, platform) với platform ∈ {taobao, 1688}."""
    norm = normalize_product_import_url((raw or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    if not _PANDAMALL_HOST_RE.fullmatch(p.hostname or ""):
        return None
    m = _PANDAMALL_DETAIL_RE.match(p.path or "")
    if not m:
        return None
    platform = m.group(1).lower()
    item_id = (m.group(2) or "").strip()
    if not item_id.isdigit():
        return None
    return item_id, platform


def build_pandamall_taobao_pdp_url(item_id: str) -> str:
    oid = str(item_id or "").strip()
    return f"https://pandamall.vn/taobao/detail/{oid}" if oid.isdigit() else ""


def build_pandamall_1688_pdp_url(offer_id: str) -> str:
    oid = str(offer_id or "").strip()
    return f"https://pandamall.vn/1688/detail/{oid}" if oid.isdigit() else ""


def resolve_pandamall_import_url(raw: str) -> Tuple[str, str]:
    """Chuẩn hoá link → (pandamall_pdp_url, platform)."""
    trimmed = (raw or "").strip()
    detail = extract_pandamall_detail(trimmed)
    if detail:
        item_id, platform = detail
        url = (
            build_pandamall_taobao_pdp_url(item_id)
            if platform == PANDAMALL_PLATFORM_TAOBAO
            else build_pandamall_1688_pdp_url(item_id)
        )
        return url, platform

    norm = normalize_product_import_url(trimmed)
    if not norm:
        raise ImportPandamallError("Link PandaMall/Taobao/1688 không hợp lệ.")

    tid = parse_t_prefixed_item_id(norm) or extract_taobao_tmall_item_id(norm)
    if tid:
        return build_pandamall_taobao_pdp_url(tid), PANDAMALL_PLATFORM_TAOBAO

    slug = extract_hibox_slug(norm)
    if slug and slug != "hibox_import":
        abb = extract_hibox_1688_offer_digits(slug)
        if abb:
            return build_pandamall_1688_pdp_url(abb), PANDAMALL_PLATFORM_1688
        if re.fullmatch(r"\d+", slug):
            return build_pandamall_taobao_pdp_url(slug), PANDAMALL_PLATFORM_TAOBAO

    oid1688 = extract_offer_id(norm)
    if oid1688 and oid1688.isdigit():
        return build_pandamall_1688_pdp_url(oid1688), PANDAMALL_PLATFORM_1688

    raise ImportPandamallError(
        "Không quy đổi được sang PandaMall. Cần link pandamall.vn/taobao|1688/detail/{id}, "
        "Taobao/Tmall, T{id}, Hibox, hoặc offer 1688."
    )


def pandamall_canonical_import_url(raw: str) -> str:
    try:
        url, _platform = resolve_pandamall_import_url(raw)
        return url
    except ImportPandamallError:
        detail = extract_pandamall_detail(raw)
        if detail:
            item_id, platform = detail
            return (
                build_pandamall_taobao_pdp_url(item_id)
                if platform == PANDAMALL_PLATFORM_TAOBAO
                else build_pandamall_1688_pdp_url(item_id)
            )
        return normalize_product_import_url(raw or "")


def _norm_img_url(raw: str) -> str:
    u = (raw or "").strip().strip('"').strip("'")
    if not u:
        return ""
    if u.startswith("//"):
        u = f"https:{u}"
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    u = re.sub(r"_\d+x\d+\.(jpg|jpeg|png|webp)(?=($|\?))", r".\1", u, flags=re.I)
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


def _clean_pandamall_info_texts(values: List[Any]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        s = _clean_text(raw, limit=400)
        if not s or _PANDAMALL_INFO_NOISE_RE.search(s):
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
  const upgradeImg = (raw) => {
    const u = normText(raw);
    if (!/^https?:\/\//i.test(u)) return u;
    return u.replace(/(\.(?:jpg|jpeg|png|webp))?_\d+x\d+\.(jpg|jpeg|png|webp)(?=($|\?))/i, (match, ext1, ext2) => {
        return ext1 ? ext1 : "." + ext2;
    });
  };
  const pushUnique = (arr, seen, raw) => {
    const u = upgradeImg(raw);
    if (!/^https?:\/\//i.test(u)) return;
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

  const sizes = [];
  const sizeSet = new Set();
  const pushSize = (raw) => {
    const s = normText(raw);
    if (!s || s.length > 120 || sizeSet.has(s.toLowerCase())) return;
    sizeSet.add(s.toLowerCase());
    sizes.push(s);
  };

  const colors = [];
  const seenColor = new Set();
  const pushColor = (label, imgEl, extra) => {
    const l = normText(label);
    if (!l || l.length > 160 || seenColor.has(l.toLowerCase())) return;
    seenColor.add(l.toLowerCase());
    colors.push({
      label: l,
      image_url: upgradeImg(imgUrl(imgEl)) || null,
      price_vnd: extra?.price_vnd ?? null,
      price_cny: extra?.price_cny ?? null,
      stock: extra?.stock ?? null,
      stock_text: extra?.stock_text ?? "",
      in_stock: extra?.in_stock !== false,
    });
  };

  document.querySelectorAll(".variation-values.ver-swipe, .variation-values").forEach((section) => {
    const buttons = section.querySelectorAll("button.item-value, button.ant-btn.item-value");
    if (buttons.length) {
      buttons.forEach((btn) => {
        const img = btn.querySelector("img.img-fit, img");
        const label = btn.querySelector(".label-title")?.innerText || btn.innerText || btn.textContent;
        if (img) {
          pushColor(label, img, { in_stock: true });
        } else {
          pushSize(label);
        }
      });
      return;
    }
    section.querySelectorAll(".item-property").forEach((row) => {
      const label = normText(row.querySelector(".property-name")?.innerText || row.querySelector(".property-name")?.textContent);
      if (!label) return;
      const stockText = normText(row.querySelector(".property-onsale")?.innerText || "");
      let stock = null;
      const sm = stockText.match(/(\d[\d.,]*)\s*sản phẩm/i);
      if (sm) stock = parseInt(sm[1].replace(/[^\d]/g, ""), 10);
      const priceVndText = normText(row.querySelector(".price-amount.price-vnd")?.innerText || "");
      const priceCnyText = normText(row.querySelector(".price-amount.price-cny")?.innerText || "");
      const priceVnd = parseInt(priceVndText.replace(/[^\d]/g, ""), 10) || null;
      const cnyMatch = priceCnyText.match(/([\d.,]+)/);
      const priceCny = cnyMatch ? cnyMatch[1].replace(/,/g, "") : null;
      const inStock = !/hết\s*hàng/i.test(stockText) && (stock == null || stock > 0);
      pushColor(label, row.querySelector(".image img, img.image"), {
        price_vnd: priceVnd,
        price_cny: priceCny,
        stock,
        stock_text: stockText,
        in_stock: inStock,
      });
    });
  });

  const variant_rows = [];
  const pairSeen = new Set();
  const buildRows = (colorObj, sizeLabel) => {
    const color = colorObj?.label || "";
    const size = normText(sizeLabel);
    if (!color) return;
    const key = `${color.toLowerCase()}###${size.toLowerCase()}`;
    if (pairSeen.has(key)) return;
    pairSeen.add(key);
    variant_rows.push({
      color,
      size,
      image_url: colorObj?.image_url || null,
      stock: colorObj?.stock,
      price_vnd: colorObj?.price_vnd,
      price_text: colorObj?.price_vnd ? `${colorObj.price_vnd} đ` : "",
      stock_text: colorObj?.stock_text || "",
      in_stock: colorObj?.in_stock !== false,
    });
  };
  if (colors.length && sizes.length) {
    colors.forEach((c) => {
      if (c.in_stock === false) return;
      sizes.forEach((sz) => buildRows(c, sz));
    });
  } else if (colors.length) {
    colors.forEach((c) => {
      if (c.in_stock === false) return;
      buildRows(c, "");
    });
  }

  const layout_mode = sizes.length ? (colors.length ? "color_size" : "size_only") : (colors.length ? "color_only" : "unknown");

  const gallery = [];
  const seenGallery = new Set();
  const collectThumbGallery = () => {
    const slides = Array.from(
      document.querySelectorAll(".swiper-wrapper .swiper-slide:not(.swiper-slide-duplicate)")
    ).filter((slide) => {
      const img = slide.querySelector("img.img-fit, img");
      if (!img) return false;
      const alt = normText(img.getAttribute("alt") || "");
      if (/^thumb-\d+$/i.test(alt)) return true;
      const src = imgUrl(img);
      return /_\d+x\d+\.(jpg|jpeg|png|webp)(?=($|\?))/i.test(src);
    });
    slides
      .sort((a, b) => {
        const ai = parseInt(a.getAttribute("data-swiper-slide-index") || "0", 10);
        const bi = parseInt(b.getAttribute("data-swiper-slide-index") || "0", 10);
        return ai - bi;
      })
      .forEach((slide) => {
        const img = slide.querySelector("img.img-fit, img");
        if (img) pushUnique(gallery, seenGallery, imgUrl(img));
      });
  };
  collectThumbGallery();

  const detailImages = [];
  const seenDetail = new Set();
  const detailDebug = [];
  const collectDetailImages = () => {
    const allNodes = Array.from(document.querySelectorAll("body *"));
    const nodeText = (el) => normText(el.innerText || el.textContent);
    const title = allNodes.find((el) => {
      const t = nodeText(el);
      return t === "Mô tả sản phẩm" || t === "Mo ta san pham";
    });
    if (!title) { detailDebug.push("No title found"); return; }
    detailDebug.push("Found title: " + title.tagName + "." + title.className + " -> " + (title.outerHTML || "").substring(0, 100));

    const isAfter = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const isBefore = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_PRECEDING);
    const stop = allNodes.find((el) => {
      const t = nodeText(el);
      if (t !== "Thu gọn" && t !== "thu gọn") return false;
      return isAfter(title, el);
    });
    detailDebug.push("Stop found: " + !!stop);

    document.querySelectorAll("img[src*='alicdn'], img[src*='cbu01'], img[src*='ibank'], img[src*='taobaocdn']").forEach((img) => {
      if (!isAfter(title, img)) return;
      if (stop && !isBefore(stop, img)) return;
      if (img.closest(".swiper-wrapper, .variation-values, .item-property")) return;
      
      const rect = img.getBoundingClientRect();
      const w = rect.width || img.naturalWidth || 0;
      const h = rect.height || img.naturalHeight || 0;
      if (w > 0 && h > 0 && (w < 60 || h < 60)) return;
      
      pushUnique(detailImages, seenDetail, imgUrl(img));
    });
  };
  collectDetailImages();

  const infoPairs = [];
  const seenInfo = new Set();
  document.querySelectorAll(".item-description_table .ant-row").forEach((row) => {
    let currentTitle = "";
    Array.from(row.children).forEach((el) => {
      const isTitle = el.classList.contains('title');
      const isProp = el.classList.contains('property');
      const text = normText(el.innerText || el.textContent);
      
      if (isTitle) {
        currentTitle = text;
      } else if (isProp && currentTitle) {
        const line = text ? `${currentTitle}: ${text}` : currentTitle;
        if (line && line.length >= 3 && line.length <= 400 && !/Hiển thị đầy đủ|Thu gọn|Thêm giỏ|Mua ngay/i.test(line)) {
          if (!seenInfo.has(line)) {
            seenInfo.add(line);
            infoPairs.push(line);
          }
        }
        currentTitle = "";
      }
    });
  });

  const priceTexts = [];
  document.querySelectorAll(".price-amount.price-vnd, .number-price .price-vnd, [class*='price']").forEach((el) => {
    const t = normText(el.innerText || el.textContent);
    if (/\d/.test(t) && /đ|₫|vnd/i.test(t)) priceTexts.push(t);
  });

  const cnyPriceTexts = [];
  document.querySelectorAll(".price-amount.price-cny").forEach((el) => {
    const t = normText(el.innerText || el.textContent);
    const m = t.match(/([\d.,]+)/);
    if (m) cnyPriceTexts.push(m[1].replace(/,/g, ""));
  });

  let videoUrl = "";
  document.querySelectorAll("video source[src], video[src]").forEach((el) => {
    if (videoUrl) return;
    videoUrl = normText(el.getAttribute("src") || el.src || "");
  });

  const descriptionText = (() => {
    const allNodes = Array.from(document.querySelectorAll("body *"));
    const nodeText = (el) => normText(el.innerText || el.textContent);
    const start = allNodes.find((el) => nodeText(el) === "Mô tả sản phẩm");
    if (!start) return "";
    const isAfter = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const stop = allNodes.find((el) => {
      const t = nodeText(el);
      return (t === "Thu gọn" || t === "thu gọn") && isAfter(start, el);
    });
    const parts = [];
    allNodes.forEach((el) => {
      if (!isAfter(start, el)) return;
      if (stop && el.compareDocumentPosition(stop) & Node.DOCUMENT_POSITION_FOLLOWING) return;
      if (el.tagName === "IMG") return;
      const t = nodeText(el);
      if (!t || t.length > 2000) return;
      if (/^Mô tả sản phẩm$|^Thu gọn$|^Hiển thị đầy đủ/i.test(t)) return;
      parts.push(t);
    });
    return parts.join("\n").slice(0, 12000);
  })();

  return {
    page_url: window.location.href,
    title: titleCandidates[0] || "",
    document_title: document.title || "",
    meta_title: meta("title"),
    meta_description: meta("description"),
    meta_image: meta("image"),
    body_text_sample: text.slice(0, 16000),
    colors,
    sizes,
    variant_rows,
    gallery_images: gallery,
    detail_images: detailImages,
    debug_detail: detailDebug,
    info_texts: infoPairs.slice(0, 80),
    price_texts: priceTexts.slice(0, 20),
    cny_price_texts: cnyPriceTexts.slice(0, 12),
    description_text: descriptionText,
    video_url: videoUrl,
    layout_mode,
  };
}"""


_SCROLL_VARIATION_PANELS_JS = r"""() => {
  document.querySelectorAll(".variation-values.ver-swipe, .variation-values").forEach((panel) => {
    try {
      const step = Math.max(80, Math.floor((panel.scrollHeight || 0) / 4));
      for (let y = 0; y <= (panel.scrollHeight || 0) + step; y += step) {
        panel.scrollTop = y;
      }
      panel.scrollTop = panel.scrollHeight || 0;
    } catch (_) {}
  });
}"""


def _scroll_pandamall_variation_panels(page: Any) -> None:
    import time
    for _ in range(5):
        page.keyboard.press("PageDown")
        time.sleep(0.5)
    try:
        page.evaluate(_SCROLL_VARIATION_PANELS_JS)
        page.wait_for_timeout(800)
        page.evaluate(_SCROLL_VARIATION_PANELS_JS)
        page.wait_for_timeout(500)
    except Exception:
        pass


def _click_expand_button(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
              // Try to find the button by text
              const els = [...document.querySelectorAll("button, span, div, a")];
              let el = els.find((x) => (x.innerText || x.textContent || "").trim() === "Hiển thị đầy đủ mô tả");
              
              // Fallback to checking the expand class
              if (!el) {
                  const expandDiv = document.querySelector(".item-description_expand, .expand-btn");
                  if (expandDiv) el = expandDiv.querySelector("button, span") || expandDiv;
              }
              
              if (el) { 
                  el.click(); 
                  return true; 
              }
              return false;
            }"""
            )
        )
    except Exception:
        return False


def scrape_pandamall_for_import(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    return run_import_playwright_sync(lambda: _scrape_pandamall_for_import_sync(source_url))


def _scrape_pandamall_for_import_sync(source_url: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    import time
    page_url, platform = resolve_pandamall_import_url(source_url)
    detail = extract_pandamall_detail(page_url) or extract_pandamall_detail(source_url)
    item_id = detail[0] if detail else ""

    warnings: List[str] = []
    raw: Dict[str, Any] = {}
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportPandamallError("Thiếu Playwright để scrape PandaMall.") from exc

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
                    prefer_hosts={"pandamall.vn"},
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

                # Tự động đăng nhập nếu bị đẩy ra trang login hoặc thấy form
                if "login" in page.url.lower() or page.locator("text=Đăng nhập").count() > 0 or page.get_by_placeholder("Số điện thoại/Email").count() > 0:
                    from app.services.import_scraper_cookies import get_pandamall_account
                    acc = get_pandamall_account()
                    username = acc.get("username", "")
                    password = acc.get("password", "")

                    if username and password:
                        try:
                            # Đảm bảo các field tồn tại trước khi điền
                            if page.get_by_placeholder("Số điện thoại/Email").count() > 0:
                                page.get_by_placeholder("Số điện thoại/Email").fill(username)
                                page.get_by_placeholder("Mật khẩu").fill(password)
                                page.get_by_role("button", name="Đăng nhập").first.click()
                                page.wait_for_timeout(3000)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=15000)
                                except Exception:
                                    pass
                                # Nếu sau khi đăng nhập bị kẹt ở trang chủ, chuyển hướng lại về sản phẩm
                                if "detail" not in page.url.lower():
                                    page.goto(page_url, wait_until="domcontentloaded", timeout=45_000)
                                    try:
                                        page.wait_for_load_state("networkidle", timeout=15000)
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"PandaMall auto-login failed: {e}")

                page.wait_for_timeout(2500)
                for y in (500, 1200, 2200, 3600):
                    page.evaluate("([yy]) => window.scrollTo(0, yy)", [y])
                    page.wait_for_timeout(650)
                page.evaluate("() => window.scrollTo(0, 0)")
                page.wait_for_timeout(600)
                _scroll_pandamall_variation_panels(page)

                if _click_expand_button(page):
                    time.sleep(3.0)
                else:
                    time.sleep(1.5)
                for y in (800, 1800, 3200, 5200, 7600):
                    page.evaluate("([yy]) => window.scrollTo(0, yy)", [y])
                    page.wait_for_timeout(600)
                raw = page.evaluate(_SCRAPE_JS)
            finally:
                for cleanup in (page.close, context.close, browser.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
    except Exception as exc:
        detail_msg = str(exc).strip() or repr(exc) or type(exc).__name__
        if "Executable doesn't exist" in detail_msg or "playwright install" in detail_msg.lower():
            detail_msg = (
                f"{detail_msg} — Trên server (Linux): "
                "cd backend && source .venv/bin/activate && python -m playwright install chromium "
                "(hoặc: bash deploy/install-playwright-browsers.sh từ root repo)."
            )
        raise ImportPandamallError(f"Lỗi Playwright/PandaMall: {detail_msg}") from exc

    if not isinstance(raw, dict):
        raise ImportPandamallError("Scraper PandaMall trả về dữ liệu không hợp lệ.")

    page_text = " ".join(str(raw.get(k) or "") for k in ("title", "document_title", "body_text_sample")).lower()
    if any(token in page_text for token in _BLOCK_MARKERS):
        raise ImportPandamallError("PandaMall đang chặn/CAPTCHA hoặc không cho tải PDP.")

    product_data = pandamall_row_to_product_data(raw, page_url, item_id, platform=platform)
    if not product_data.get("colors"):
        warnings.append("PandaMall: chưa thu được màu từ .item-property / .variation-values.")
    elif not product_data.get("sizes") and product_data.get("product_info", {}).get("variants", {}).get("variant_only"):
        n_colors = len(product_data.get("colors") or [])
        if n_colors:
            warnings.append(
                f"PandaMall: layout chỉ màu/biến thể (túi, phụ kiện…) — {n_colors} màu, không có size."
            )
    if not product_data.get("sizes") and not product_data.get("colors"):
        warnings.append("PandaMall: chưa thu được size/màu từ trang chi tiết.")
    if not product_data.get("gallery"):
        warnings.append("PandaMall: chưa thu được gallery từ swiper.")
    return raw, product_data, warnings


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
    for c in row.get("colors") or []:
        if isinstance(c, dict) and c.get("price_cny"):
            s = str(c.get("price_cny") or "").strip().replace(",", "")
            try:
                val = float(s)
            except ValueError:
                continue
            if 0 < val < 9_999_999:
                return f"{val:.4f}".rstrip("0").rstrip(".")
    return _estimate_cny_from_vnd(price_vnd)


def _is_variant_in_stock(r: Dict[str, Any]) -> bool:
    if r.get("in_stock") is False:
        return False
    stock_text = _clean_text(r.get("stock_text") or "", limit=160)
    if re.search(r"hết\s*hàng", stock_text, re.I):
        return False
    try:
        stock = int(r.get("stock") or 0)
    except (TypeError, ValueError):
        stock = 0
    if stock > 0:
        return True
    if re.search(r"có\s*sẵn|sản phẩm", stock_text, re.I):
        return True
    return r.get("in_stock") is True


def _pandamall_variant_rows_are_color_only(variant_rows: List[Dict[str, Any]]) -> bool:
    return bool(variant_rows) and all(not _clean_text(r.get("size"), limit=80) for r in variant_rows)


def _pandamall_layout_is_color_only(row: Dict[str, Any], variant_rows: List[Dict[str, Any]]) -> bool:
    layout = str(row.get("layout_mode") or "").strip().lower()
    if layout == "color_only":
        return True
    scraped_sizes = [_clean_text(s, limit=80) for s in row.get("sizes") or [] if _clean_text(s, limit=80)]
    if scraped_sizes:
        return False
    return _pandamall_variant_rows_are_color_only(variant_rows)


def pandamall_row_to_product_data(
    row: Dict[str, Any],
    source_url: str,
    item_id: str,
    *,
    platform: str = PANDAMALL_PLATFORM_1688,
) -> Dict[str, Any]:
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

    variant_rows = [r for r in row.get("variant_rows") or [] if isinstance(r, dict) and _is_variant_in_stock(r)]

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

    color_only_layout = _pandamall_layout_is_color_only(row, variant_rows)

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
        if color_only_layout:
            if color:
                pair_objs.append({"color": color, "size": ""})
        elif color and size:
            pair_objs.append({"color": color, "size": size})
        if not color_only_layout and size and size.lower() not in seen_size:
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

    if in_stock_raw_colors:
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

    if not color_only_layout:
        if not sizes:
            sizes = [_clean_text(s, limit=80) for s in row.get("sizes") or [] if _clean_text(s, limit=80)]
        else:
            scraped_sizes = [_clean_text(s, limit=80) for s in row.get("sizes") or [] if _clean_text(s, limit=80)]
            if scraped_sizes:
                sizes = scraped_sizes
        if colors_out and sizes:
            pair_objs = []
            for c in colors_out:
                cname = _clean_text(c.get("name"), limit=160)
                if not cname:
                    continue
                for sz in sizes:
                    pair_objs.append({"color": cname, "size": sz})
    else:
        sizes = []
        if not pair_objs:
            pair_objs = [{"color": c.get("name", ""), "size": ""} for c in colors_out if c.get("name")]

    price_vnd = min(prices) if prices else 0.0
    if price_vnd <= 0:
        for t in row.get("price_texts") or []:
            price_vnd = _parse_vnd_price(t)
            if price_vnd > 0:
                break

    main_image = (gallery[0] if gallery else "") or (colors_out[0]["img"] if colors_out else "") or meta_image
    if not gallery and main_image:
        gallery = [main_image]

    title = _clean_text(row.get("title") or row.get("meta_title") or row.get("document_title"), limit=500)
    if "pandamall" in title.lower() and "-" in title:
        title = title.split("-", 1)[0].strip() or title
    if not title:
        title = f"{'Taobao' if platform == PANDAMALL_PLATFORM_TAOBAO else '1688'} {item_id}"

    is_taobao = platform == PANDAMALL_PLATFORM_TAOBAO
    supply_slug = item_id if is_taobao else f"abb-{item_id}"
    supply_url = supply_product_link_default_for_hibox_slug(supply_slug)
    if not is_taobao and item_id.isdigit():
        supply_url = canonical_1688_offer_pc_url(item_id) or supply_url
    product_id = build_canonical_hibox_product_id(item_id) if is_taobao else f"A{item_id}"
    origin = "taobao" if is_taobao else "1688"
    supply_platform = "taobao" if is_taobao else "1688"
    cny_for_excel = _pick_cny_price(row, price_vnd)

    info_texts = _clean_pandamall_info_texts(row.get("info_texts") or [])
    variant_context_parts: List[str] = []
    if colors_out:
        label = "Biến thể" if color_only_layout else "Màu sắc"
        variant_context_parts.append(
            f"{label}: " + ", ".join([c.get("name", "") for c in colors_out if c.get("name")])
        )
    if sizes:
        variant_context_parts.append("Kích cỡ: " + ", ".join(sizes))
    supplier_specs_excerpt = "\n".join([*variant_context_parts, *info_texts[:80]]).strip()

    desc = _clean_text(row.get("description_text") or row.get("meta_description"), limit=12000)
    if info_texts:
        desc = (desc + "\n\n--- Thông số ---\n" if desc else "--- Thông số ---\n") + "\n".join(info_texts[:60])

    variants: Dict[str, Any] = {
        "pairs": pair_objs,
        "source": "pandamall",
        "supply_platform": supply_platform,
        "supply_product_url": supply_url,
        "pandamall_product_url": source_url,
        "pandamall_platform": platform,
    }
    if color_only_layout:
        variants["variant_only"] = True
    if swatches:
        variants["color_swatches"] = swatches
    if sizes:
        variants["sizes"] = sizes
    if variant_rows:
        variants["pandamall_rows"] = variant_rows[:300]

    product_info = {
        "product_info": {
            "name_original": title,
            "listing_sku_hint": product_id,
        },
        "market_info": {
            "currency": "VND",
            "pandamall_price_vnd": price_vnd or None,
            "price_cny_approx": float(_estimate_cny_from_vnd(price_vnd) or 0) or None,
            "listing_import_vnd_per_cny_used": _listing_vnd_per_cny(),
        },
        "specifications": {
            "supplier_specs_excerpt": supplier_specs_excerpt[:4000],
            "pandamall_info_texts": info_texts[:80],
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
        "shop_name": "PandaMall",
        "shop_name_chinese": None,
        "shop_id": item_id,
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
