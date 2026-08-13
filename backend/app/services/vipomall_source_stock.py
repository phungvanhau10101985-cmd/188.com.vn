"""
Fallback kiểm tra tồn nguồn qua PDP Vipomall (gương 1688).

Chỉ áp dụng khi đã suy ra được offerId 1688 (link offer/abb-*/CSSBuy item-1688 hoặc mã A{offer}; vẫn hỗ trợ mã legacy A{offer}a188…).
Tiêu chí: có nút / chữ «Thêm giỏ hàng» trong HTML tải về → còn hàng; không thấy → hết hàng nguồn.
"""

from __future__ import annotations

import logging
import re
from http.cookiejar import CookieJar
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, build_opener

from app.core.config import settings
from app.services.import_1688_scraper import extract_offer_id
from app.services.import_cssbuy_client import cssbuy_item_page_to_item_slug
from app.services.import_source_ids import (
    extract_abb_offer_digits,
    extract_legacy_mirror_slug,
    normalize_product_import_url,
)

logger = logging.getLogger(__name__)

_VIPOMALL_HOST_OK = re.compile(r"^(?:www\.)?vipomall\.vn$", re.I)
_PRODUCT_ID_A_OFFER_RE = re.compile(r"^A(\d+)(?:a188.*)?$", re.I)

_PDP_OK_MARKERS = (
    "thêm giỏ hàng",
    "them gio hang",
    "cart_detail.svg",
    "spn-color",
)

_VIPOMALL_PDP_PROBE_JS = """() => {
  const html = document.documentElement ? document.documentElement.outerHTML : "";
  const low = (html || "").toLowerCase();
  const title = document.title || "";
  const bodyText = (document.body && document.body.innerText) || "";
  const pdpOk = ["thêm giỏ hàng", "cart_detail.svg", "spn-color", "mua ngay"].some(
    (m) => low.includes(m) || bodyText.toLowerCase().includes(m)
  );
  const challenge = ["just a moment", "attention required", "cf-browser-verification", "verify you are human"].some(
    (n) => title.toLowerCase().includes(n) || low.includes(n)
  );
  const cart = document.querySelector('button.button img[src*="cart_detail.svg"]')
    || Array.from(document.querySelectorAll("button.button, span.spn-color, button")).find((el) =>
      /thêm\\s*giỏ\\s*hàng/i.test(((el.innerText || "") + "").trim())
    );
  const buy = Array.from(document.querySelectorAll("button, a, span")).find((el) =>
    /^mua ngay$/i.test(((el.innerText || "") + "").trim())
  );
  return {
    blocked: !pdpOk && challenge,
    cartFound: !!cart,
    buyFound: !!buy,
    ctaFound: !!(cart || buy),
  };
}"""


VIPOMALL_PLATFORM_1688 = 10
VIPOMALL_PLATFORM_TAOBAO = 21


def build_vipomall_pdp_url(offer_id: str, platform_type: int = VIPOMALL_PLATFORM_1688) -> str:
    oid = str(offer_id or "").strip()
    if not oid.isdigit():
        return ""
    pt = VIPOMALL_PLATFORM_TAOBAO if int(platform_type) == VIPOMALL_PLATFORM_TAOBAO else VIPOMALL_PLATFORM_1688
    return f"https://vipomall.vn/san-pham/{oid}?platform_type={pt}"


def build_vipomall_1688_pdp_url(offer_id: str) -> str:
    return build_vipomall_pdp_url(offer_id, VIPOMALL_PLATFORM_1688)


def build_vipomall_taobao_pdp_url(item_id: str) -> str:
    return build_vipomall_pdp_url(item_id, VIPOMALL_PLATFORM_TAOBAO)


_VIPOMALL_PLACEHOLDER_TITLES = frozenset(
    {
        "",
        "SẢN PHẨM MỚI",
        "SAN PHAM MOI",
        "VIPO MALL: MUA HÀNG XUYÊN BIÊN GIỚI",
        "VIPO MALL: MUA HANG XUYEN BIEN GIOI",
    }
)


def vipomall_scraped_product_looks_listed(product_data: Dict[str, Any]) -> bool:
    """
    Heuristic sau ``scrape_vipomall_for_import``: PDP thật thường có variant/ảnh;
    offer không có trên Vipomall hay trả shell «SẢN PHẨM MỚI» + gallery tối thiểu.
    """
    if not isinstance(product_data, dict):
        return False
    title = re.sub(r"\s+", " ", str(product_data.get("name") or "")).strip().upper()
    if title in _VIPOMALL_PLACEHOLDER_TITLES:
        return False
    colors = len(product_data.get("colors") or [])
    sizes = len(product_data.get("sizes") or [])
    gallery = len(product_data.get("images") or product_data.get("gallery") or [])
    return colors > 0 or sizes > 0 or gallery >= 2


def probe_vipomall_1688_offer_listed(offer_id: str) -> Tuple[bool, Optional[str]]:
    """
    Playwright mở PDP Vipomall. Trả (có_listing, lỗi_ngắn).
    """
    oid = str(offer_id or "").strip()
    if not oid.isdigit():
        return False, "offerId không phải số."
    try:
        from app.services.import_vipomall_scraper import scrape_vipomall_for_import

        _, product_data, _warnings = scrape_vipomall_for_import(build_vipomall_1688_pdp_url(oid))
        return vipomall_scraped_product_looks_listed(product_data), None
    except Exception as exc:
        return False, str(exc)[:500]


def resolve_numeric_1688_offer_id_from_source_url(
    url: str,
    *,
    fallback_product_id: Optional[str] = None,
) -> Optional[str]:
    """
    offerId thuần số từ URL nguồn (1688 / abb-* / cssbuy item-1688) hoặc từ product_id dạng A{offer}.
    Taobao/Tmall thuần (slug số, link item.taobao…) → None (không có PDP 1688 trên Vipomall theo offer).
    """
    norm = (normalize_product_import_url((url or "").strip()) or (url or "").strip()).strip()
    from app.services.import_vipomall_scraper import extract_vipomall_offer_id

    vm_oid = extract_vipomall_offer_id(norm)
    if vm_oid and vm_oid.isdigit():
        return vm_oid
    oid_url = extract_offer_id(norm)
    if oid_url and oid_url.isdigit():
        return oid_url
    slug = extract_legacy_mirror_slug(norm)
    if slug:
        abb = extract_abb_offer_digits(slug)
        if abb:
            return abb
    cs_slug = cssbuy_item_page_to_item_slug(norm)
    if cs_slug:
        abb = extract_abb_offer_digits(cs_slug)
        if abb:
            return abb
    raw_pid = (fallback_product_id or "").strip()
    m = _PRODUCT_ID_A_OFFER_RE.match(raw_pid)
    if m:
        return m.group(1)
    return None


def vipomall_html_suggests_blocked(html: str) -> bool:
    blob = re.sub(r"\s+", " ", (html or "").strip()[:120_000].lower())
    if any(m in blob for m in _PDP_OK_MARKERS):
        return False
    if len(blob) < 80:
        return True
    return any(
        marker in blob
        for marker in (
            "just a moment",
            "attention required",
            "cf-browser-verification",
            "verify you are human",
            "captcha",
            "验证码",
        )
    )


def vipomall_html_shows_add_to_cart_cta(html: str) -> bool:
    """
    PDP Vipomall (Angular): vùng «Thêm giỏ hàng» — nếu không có chuỗi / khối add-cart → coi hết hàng.
    """
    raw = html or ""
    if not raw.strip():
        return False
    low = raw.lower()
    if "thêm giỏ hàng" in low or "them gio hang" in low:
        return True
    if "th&ecirc;m giỏ h&agrave;ng" in low:
        return True
    if "cart_detail.svg" in low and ("button" in low or "giỏ hàng" in low or "spn-color" in low):
        return True
    if 'class="add-cart"' in low or "class='add-cart'" in low:
        return True
    if "list-btn" in low and "spn-color" in low and "giỏ" in low:
        return True
    return False


def fetch_vipomall_pdp_html(page_url: str, *, timeout: float = 60.0) -> Tuple[str, Optional[str]]:
    url = (page_url or "").strip()
    p = urlparse(url)
    if not _VIPOMALL_HOST_OK.match(p.hostname or "") or not (p.path or "").strip().startswith("/san-pham/"):
        return "", "URL không phải trang sản phẩm Vipomall hợp lệ (vipomall.vn/san-pham/…)."

    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", ua),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
        ("Accept-Language", "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"),
    ]
    try:
        html = opener.open(url, timeout=timeout).read().decode("utf-8", "replace")
        return html, None
    except Exception as exc:
        logger.warning("vipomall fetch failed: %s", exc)
        return "", str(exc)[:900]


def _evaluate_vipomall_pdp_stock_sync(page_url: str) -> Tuple[str, Optional[str], str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return "error", f"Thiếu Playwright để mở Vipomall: {exc}", "vipomall"

    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    headless_raw = getattr(settings, "SOURCE_STOCK_CHECK_HEADLESS", True)
    headless = str(headless_raw).strip().lower() not in {"0", "false", "no", "off"}
    timeout_ms = max(8_000, int(getattr(settings, "SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS", 90_000) or 90_000))
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
                try:
                    from app.services.import_scraper_cookies import seed_playwright_context_cookies

                    seed_playwright_context_cookies(
                        context, page, prefer_hosts={"vipomall.vn"}, target_url=page_url
                    )
                except Exception:
                    pass
                page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
                except Exception:
                    pass
                page.wait_for_timeout(1_800)
                html0 = page.content() or ""
                if vipomall_html_suggests_blocked(html0) and not vipomall_html_shows_add_to_cart_cta(html0):
                    title0 = ""
                    try:
                        title0 = page.title() or ""
                    except Exception:
                        pass
                    if "just a moment" in title0.lower():
                        return (
                            "blocked",
                            "Vipomall bị Cloudflare / CAPTCHA — fallback PandaMall.",
                            "vipomall",
                        )
                try:
                    page.locator("button.button, span.spn-color, img[src*='cart_detail.svg']").first.wait_for(
                        state="visible", timeout=min(18_000, timeout_ms)
                    )
                except Exception:
                    pass
                snap = page.evaluate(_VIPOMALL_PDP_PROBE_JS)
                html1 = page.content() or html0
                if isinstance(snap, dict) and snap.get("blocked"):
                    return (
                        "blocked",
                        "Vipomall bị Cloudflare / CAPTCHA — fallback PandaMall.",
                        "vipomall",
                    )
                if (isinstance(snap, dict) and snap.get("ctaFound")) or vipomall_html_shows_add_to_cart_cta(html1):
                    return "in_stock", None, "vipomall"
                return (
                    "out_of_stock",
                    "Vipomall: không thấy nút «Thêm giỏ hàng» / «Mua ngay» — coi hết hàng.",
                    "vipomall",
                )
            finally:
                for cleanup in (page.close, context.close, browser.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
    except Exception as exc:
        detail = str(exc).strip() or repr(exc)
        low = detail.lower()
        if any(n in low for n in ("captcha", "cloudflare", "cf-ray", "challenge", "access denied")):
            return (
                "blocked",
                ("Vipomall bị chặn bảo mật / CAPTCHA / Cloudflare — fallback PandaMall. " + detail)[:1000],
                "vipomall",
            )
        return "error", f"Lỗi Playwright/Vipomall: {detail}"[:1000], "vipomall"


def evaluate_vipomall_1688_offer_stock(offer_id: str) -> Tuple[str, Optional[str], str]:
    """Playwright: nút «Thêm giỏ hàng» (cart_detail.svg) tải được → còn hàng, kể cả disabled."""
    url = build_vipomall_1688_pdp_url(offer_id)
    if not url:
        return "error", "Không có offerId 1688 hợp lệ để kiểm tra Vipomall.", "vipomall"
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    timeout_sec = max(30.0, (int(getattr(settings, "SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS", 90_000) or 90_000) / 1000.0) + 45.0)
    return run_import_playwright_sync(lambda: _evaluate_vipomall_pdp_stock_sync(url), timeout_sec=timeout_sec)


def evaluate_vipomall_source_stock_from_url(
    raw_url: str, *, fallback_product_id: Optional[str] = None
) -> Tuple[str, Optional[str], str]:
    from app.services.import_batch_url_coercion import FETCH_TARGET_VIPOMALL, coerce_url_for_excel_batch_import

    page, err = coerce_url_for_excel_batch_import((raw_url or "").strip(), FETCH_TARGET_VIPOMALL)
    if err or not (page or "").strip():
        oid = resolve_numeric_1688_offer_id_from_source_url(
            raw_url, fallback_product_id=fallback_product_id
        )
        if not oid:
            return "error", f"Không quy đổi được sang Vipomall: {err or 'thiếu offerId'}."[:1000], "vipomall"
        page = build_vipomall_1688_pdp_url(oid)
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    timeout_sec = max(30.0, (int(getattr(settings, "SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS", 90_000) or 90_000) / 1000.0) + 45.0)
    return run_import_playwright_sync(
        lambda: _evaluate_vipomall_pdp_stock_sync((page or "").strip()),
        timeout_sec=timeout_sec,
    )


def vipomall_gather_admin_batch_scan(
    db: Any,
    *,
    seed_url: str,
    fallback_product_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cùng dạng trả về với _gather_platform_scan_attempt để ghép dual-fallback admin batch.
    """
    from app.services.admin_source_stock_batch import _find_products_for_item_slug
    normalized_in = normalize_product_import_url((seed_url or "").strip())
    canonical_url = (normalized_in or (seed_url or "").strip()).strip()
    oid = resolve_numeric_1688_offer_id_from_source_url(
        canonical_url, fallback_product_id=fallback_product_id
    )
    if not oid:
        return {
            "canonical_url": canonical_url,
            "domain": "vipomall",
            "raw_status": "bad_url",
            "classified_out_of_stock": False,
            "detail": "Không suy ra được offerId 1688 — không thể kiểm tra qua Vipomall (chỉ hỗ trợ link 1688 / abb-* / CSSBuy item-1688 hoặc mã A{offer}).",
            "warnings": [],
            "matched_orm": [],
        }

    vm_url = build_vipomall_1688_pdp_url(oid)
    matched: List[Any] = list(_find_products_for_item_slug(db, f"abb-{oid}"))
    st, err, _via = evaluate_vipomall_1688_offer_stock(oid)
    if st == "in_stock":
        return {
            "canonical_url": vm_url,
            "domain": "vipomall",
            "raw_status": "ok",
            "classified_out_of_stock": False,
            "detail": None,
            "warnings": [],
            "matched_orm": matched,
        }
    if st == "out_of_stock":
        return {
            "canonical_url": vm_url,
            "domain": "vipomall",
            "raw_status": "no_data",
            "classified_out_of_stock": True,
            "detail": err,
            "warnings": [],
            "matched_orm": matched,
        }
    if st == "blocked":
        return {
            "canonical_url": vm_url,
            "domain": "vipomall",
            "raw_status": "fetch_error",
            "classified_out_of_stock": False,
            "detail": err,
            "warnings": [],
            "matched_orm": matched,
        }
    return {
        "canonical_url": vm_url,
        "domain": "vipomall",
        "raw_status": "bad_url",
        "classified_out_of_stock": False,
        "detail": err or "Vipomall: lỗi không xác định.",
        "warnings": [],
        "matched_orm": matched,
    }
