"""
Đọc dữ liệu SP qua CSSBuy.

Import catalog: GET trang ``item-*.html`` + POST ``/web/item`` (CSRF cookie).

Kiểm tra tồn nguồn: Playwright mở PDP SPA ``/shop/goodsDetail?type=&id=``, bấm
«I accept the risks», rồi đọc nút «Add to Cart» / «Buy now» (tải được nút → còn hàng, kể cả disabled).

URL chuẩn:
  • 1688 offer → ``item-1688-{offerId}.html`` hoặc ``/shop/goodsDetail?type=1688&id={offerId}``
  • Taobao/Tmall id → ``item-{itemId}.html`` hoặc ``goodsDetail?type=taobao&id=``
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

from app.services.import_source_ids import (
    extract_abb_offer_digits,
    is_legacy_placeholder_slug,
    normalize_product_import_url,
)

logger = logging.getLogger(__name__)

_CSSBUY_HOST_OK = re.compile(r"(?i)^(?:www\.)?cssbuy\.com$")


class ImportCssbuyError(RuntimeError):
    pass


class CssbuySecurityBlocked(ImportCssbuyError):
    """Cloudflare / CAPTCHA / WAF — fallback nền khác; chỉ dừng khi mọi nền đều bị chặn."""


_CSSBUY_SECURITY_BLOCK_NEEDLES = (
    "just a moment",
    "attention required",
    "cf-browser-verification",
    "cf-challenge-running",
    "checking if the site connection is secure",
    "verify you are human",
    "enable javascript and cookies to continue",
    "sorry, you have been blocked",
    "access denied",
    "安全验证",
    "验证码",
)

_CSSBUY_PDP_OK_MARKERS = (
    "add to cart",
    "i accept the risks",
    "shop_detail",
    "purchase quantity",
)

_CSSBUY_PDP_PROBE_JS = """() => {
  const html = document.documentElement ? document.documentElement.outerHTML : "";
  const low = (html || "").toLowerCase();
  const title = document.title || "";
  const href = location.href || "";
  const bodyText = (document.body && document.body.innerText) || "";
  const blockNeedles = %s;
  const pdpOk = ["add to cart", "i accept the risks", "shop_detail", "purchase quantity"].some((m) => low.includes(m) || bodyText.toLowerCase().includes(m));
  const blocked = !pdpOk && (title.toLowerCase().includes("just a moment") || title.toLowerCase().includes("attention required") || blockNeedles.some((n) => low.includes(n) || title.toLowerCase().includes(n)));
  const nodes = Array.from(document.querySelectorAll("div,button,a,p,span"));
  const exact = (el, re) => re.test(((el.innerText || "") + "").trim());
  const cartEl = document.querySelector("div.ty_button_btn6, .ty_button_btn6")
    || nodes.find((el) => exact(el, /^add to cart$/i));
  const buyEl = document.querySelector("div.ty_button_btn1, .ty_button_btn1")
    || nodes.find((el) => exact(el, /^buy now$/i));
  const cart = cartEl || buyEl || null;
  const looksLikePdp = !!(
    document.querySelector(".shop_detail,.shop_right,.shop_info,.btn_info,.shop_detail_content,.ty_button_btn6,.group-btn")
    || /inventory/i.test(bodyText)
    || /purchase quantity/i.test(bodyText)
    || /add to cart/i.test(bodyText)
    || /buy now/i.test(bodyText)
  );
  return {
    blocked: !!blocked,
    title,
    href,
    htmlLen: (html || "").length,
    looksLikePdp,
    addToCartFound: !!(cartEl || buyEl),
    addToCartDisabled: false,
    addToCartClass: cart ? String(cart.className || "") : "",
    hasAcceptRisks: /i accept the risks/i.test(bodyText),
  };
}""" % (json.dumps(list(_CSSBUY_SECURITY_BLOCK_NEEDLES)),)


@dataclass
class CssbuyPdpStockProbe:
    status: str
    error: Optional[str] = None
    clicked_accept_risks: bool = False
    add_to_cart_found: bool = False
    add_to_cart_disabled: bool = False


def parse_cssbuy_goods_detail(raw: str) -> Optional[Tuple[str, str]]:
    """``/shop/goodsDetail?type=1688&id=1006…`` → ``('1688', '1006…')``."""
    try:
        p = urlparse(normalize_product_import_url((raw or "").strip()))
    except Exception:
        return None
    if not _CSSBUY_HOST_OK.match(p.hostname or ""):
        return None
    path = (p.path or "").rstrip("/").lower()
    if not path.endswith("/shop/goodsdetail") and path != "/shop/goodsdetail":
        if "/goodsdetail" not in path:
            return None
    qs = parse_qs(p.query or "")
    typ = ""
    iid = ""
    for key, vals in qs.items():
        kl = (key or "").strip().lower()
        val = ((vals[0] if vals else "") or "").strip()
        if kl == "type":
            typ = val.lower()
        elif kl in {"id", "itemid", "item_id"}:
            iid = val
    if not iid.isdigit():
        return None
    if typ in {"1688", "alibaba"}:
        return "1688", iid
    if typ in {"taobao", "tmall", "tb"}:
        return "taobao", iid
    return "1688", iid


def cssbuy_goods_detail_url(typ: str, item_id: str) -> str:
    t = (typ or "1688").strip().lower() or "1688"
    if t in {"alibaba"}:
        t = "1688"
    if t in {"tb", "tmall"}:
        t = "taobao"
    iid = (item_id or "").strip()
    return f"https://www.cssbuy.com/shop/goodsDetail?type={t}&id={iid}"


def cssbuy_playwright_pdp_url(raw: str) -> Optional[str]:
    """URL SPA thật để Playwright mở (goodsDetail). ``item-1688-`` redirect về đây."""
    gd = parse_cssbuy_goods_detail(raw)
    if gd:
        return cssbuy_goods_detail_url(gd[0], gd[1])
    slug = cssbuy_item_page_to_item_slug(raw)
    if not slug:
        return None
    oid = extract_abb_offer_digits(slug)
    if oid:
        return cssbuy_goods_detail_url("1688", oid)
    if slug.isdigit():
        return cssbuy_goods_detail_url("taobao", slug)
    return None


def is_cssbuy_pdp_url(raw: str) -> bool:
    return is_cssbuy_item_url(raw) or parse_cssbuy_goods_detail(raw) is not None


def cssbuy_html_suggests_security_block(html: str, *, title: str = "", url: str = "") -> bool:
    """True khi đây là trang chặn CF/CAPTCHA — không phải PDP có Turnstile script nền."""
    title_l = (title or "").strip().lower()
    if "just a moment" in title_l or "attention required" in title_l:
        return True
    blob = " ".join(
        (
            re.sub(r"\s+", " ", (html or "")[:80_000].lower()),
            title_l,
            (url or "").lower(),
        )
    )
    if any(m in blob for m in _CSSBUY_PDP_OK_MARKERS):
        return False
    return any(n in blob for n in _CSSBUY_SECURITY_BLOCK_NEEDLES)


def classify_cssbuy_add_to_cart_cta(*, found: bool, disabled: bool = False, looks_like_pdp: bool = False) -> str:
    """Tải được nút Add to Cart / Buy now → còn hàng, kể cả disabled."""
    _ = (disabled, looks_like_pdp)
    return "in_stock" if found else "out_of_stock"


def is_cssbuy_item_url(raw: str) -> bool:
    try:
        p = urlparse(normalize_product_import_url((raw or "").strip()))
        if not _CSSBUY_HOST_OK.match(p.hostname or ""):
            return False
        path = (p.path or "").lower()
        return "item-" in path and path.endswith(".html")
    except Exception:
        return False


def item_slug_to_cssbuy_item_url(slug: str) -> Optional[str]:
    """abb-922… → item-1688-922… ; chỉ số → item-{id}.html"""
    s = (slug or "").strip()
    if not s or is_legacy_placeholder_slug(s):
        return None
    oid = extract_abb_offer_digits(s)
    if oid:
        return f"https://www.cssbuy.com/item-1688-{oid}.html"
    if s.isdigit():
        return f"https://www.cssbuy.com/item-{s}.html"
    return None


def cssbuy_item_page_to_item_slug(item_page_url: str) -> Optional[str]:
    """Map CSSBuy item / goodsDetail page → abb-* / digits slug for product matching."""
    gd = parse_cssbuy_goods_detail(item_page_url)
    if gd:
        typ, iid = gd
        return f"abb-{iid}" if typ == "1688" else iid
    p = urlparse(normalize_product_import_url((item_page_url or "").strip()))
    path = (p.path or "").strip("/").lower()
    if not path.endswith(".html"):
        return None
    base = path[: -len(".html")]
    parts = base.split("-")
    if len(parts) >= 3 and parts[0] == "item" and parts[1] == "1688":
        oid = parts[2]
        return f"abb-{oid}" if oid.isdigit() else None
    if len(parts) >= 2 and parts[0] == "item":
        tail = parts[-1]
        return tail if tail.isdigit() else None
    return None


_CSSBUY_DISCLAIMER_AGREEMENT_LOWER = (
    "i have read the above disclaimer and your terms of service, and i agree to both."
)


def cssbuy_html_shows_purchase_disclaimer_agreement(html: str) -> bool:
    """
    Theo PDP cssbuy.com: checkbox / vùng thoả thuận trước khi mua với đoạn văn cố định phía trên CTA giỏ hàng.

    Chuẩn hoá whitespace để không phụ thuộc `<br>` hay khoảng trắng trong markup.
    """
    raw = (html or "").strip()
    if not raw:
        return False
    blob = re.sub(r"\s+", " ", raw.lower().replace("&nbsp;", " "))
    return _CSSBUY_DISCLAIMER_AGREEMENT_LOWER in blob


def cssbuy_html_shows_add_to_cart_button(html: str) -> bool:
    """
    Theo PDP cssbuy.com: nút «Add To Cart» (khoanh đỏ để kiểm tra còn bán được hay không).

    Kiểm tra trên HTML tĩnh từ GET trang item (Vue thường đã SSR/hydrate vào markup).
    Có bản PDP dùng vùng ``div.catbuy`` + ``p.button`` chứa chữ «Add To Cart» (không phải ``<button>``).
    """
    blob = (html or "").strip().lower()
    if not blob:
        return False
    if (
        '<p class="button">add to cart</p>' in blob
        or "<p class='button'>add to cart</p>" in blob
    ):
        return True
    if "catbuy" in blob and "add to cart" in blob:
        if '<p class="button"' in blob or "<p class='button'" in blob:
            return True
    needles = (
        ">add to cart<",
        "> add to cart <",
        "add to cart</button",
        "add to cart</a",
        ">add&nbsp;to&nbsp;cart<",
        '"add to cart"',
        "'add to cart'",
        "add-to-cart",
        ">addtocart<",
        "btn-addtocart",
    )
    for n in needles:
        if n in blob:
            return True
    if "add to cart" in blob and "<button" in blob:
        return True
    return False


def cssbuy_html_disclaimer_agreement_without_add_to_cart(html: str) -> bool:
    """Đoạn disclaimer đồng ý có trong HTML nhưng không thấy CTA «Add To Cart» — PDP kiểu hết hàng / không mua được."""
    return cssbuy_html_shows_purchase_disclaimer_agreement(html) and (
        not cssbuy_html_shows_add_to_cart_button(html)
    )


def canonical_cssbuy_item_url(raw: str) -> str:
    p = urlparse(normalize_product_import_url((raw or "").strip()))
    path = (p.path or "").split("?")[0] or "/"
    return f"https://www.cssbuy.com{path if path.startswith('/') else '/' + path}"


def fetch_cssbuy_item_json_bundle(item_page_url: str) -> Tuple[Dict[str, Any], str]:
    """GET HTML + POST ``/web/item``. Trả (JSON đã parse + HTML PDP để kiểm tra CTA giỏ / disclaimer đồng ý.)"""
    if parse_cssbuy_goods_detail(item_page_url):
        mapped = item_slug_to_cssbuy_item_url(cssbuy_item_page_to_item_slug(item_page_url) or "")
        if mapped:
            item_page_url = mapped
    url = canonical_cssbuy_item_url(item_page_url)
    if not is_cssbuy_item_url(url):
        raise ImportCssbuyError("URL không phải trang item CSSBuy hợp lệ.")

    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
        ("Accept", "text/html,application/xhtml+xml"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    try:
        html = opener.open(url, timeout=60).read().decode("utf-8", "replace")
    except Exception as exc:
        raise ImportCssbuyError(f"Không tải được trang CSSBuy: {exc}") from exc

    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if not m:
        m = re.search(r'content="([^"]+)"\s+name="csrf-token"', html)
    csrf = (m.group(1) if m else "").strip()
    if not csrf:
        raise ImportCssbuyError("Không đọc được csrf-token (có thể bị chặn bot / Cloudflare).")

    slug = cssbuy_item_page_to_item_slug(url)
    if not slug:
        raise ImportCssbuyError("Không trích được itemId từ URL CSSBuy.")
    oid1688 = extract_abb_offer_digits(slug)
    if oid1688:
        typ = "1688"
        digits = oid1688
    elif slug.isdigit():
        typ = "taobao"
        digits = slug
    else:
        raise ImportCssbuyError(f"Slug không map được sang CSSBuy API: {slug!r}")

    from urllib.parse import urlencode

    body = urlencode({"type": typ, "itemId": digits, "lang": "en"}).encode()
    req = Request("https://www.cssbuy.com/web/item", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    req.add_header("X-CSRF-TOKEN", csrf)
    req.add_header("X-Requested-With", "XMLHttpRequest")
    req.add_header("Referer", url)
    req.add_header("Accept", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    )
    try:
        raw = opener.open(req, timeout=90).read().decode("utf-8", "replace")
    except Exception as exc:
        raise ImportCssbuyError(f"Lỗi gọi API /web/item: {exc}") from exc

    try:
        return json.loads(raw), html
    except json.JSONDecodeError as exc:
        logger.warning("cssbuy non-json response: %s", raw[:400])
        raise ImportCssbuyError("Phản hồi CSSBuy không phải JSON.") from exc


def fetch_cssbuy_item_json(item_page_url: str) -> Dict[str, Any]:
    """GET trang item (session + csrf), rồi POST ``/web/item`` như Vue trên trang."""
    return fetch_cssbuy_item_json_bundle(item_page_url)[0]


def _cssbuy_playwright_timeout_ms() -> int:
    try:
        from app.core.config import settings

        return max(8_000, int(getattr(settings, "SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS", 90_000) or 90_000))
    except Exception:
        return 90_000


def _cssbuy_playwright_headless() -> bool:
    try:
        from app.core.config import settings

        raw = getattr(settings, "SOURCE_STOCK_CHECK_HEADLESS", True)
        return str(raw).strip().lower() not in {"0", "false", "no", "off"}
    except Exception:
        return True


def _click_cssbuy_accept_risks(page: Any) -> bool:
    try:
        loc = page.get_by_text("I accept the risks", exact=False)
        if loc.count() > 0:
            loc.first.click(timeout=4_000)
            return True
    except Exception:
        pass
    try:
        return bool(
            page.evaluate(
                """() => {
                  const el = Array.from(document.querySelectorAll("div,button,a,span,p"))
                    .find((n) => {
                      const t = ((n.innerText || "") + "").trim();
                      return /^i accept the risks$/i.test(t);
                    });
                  if (!el) return false;
                  el.click();
                  return true;
                }"""
            )
        )
    except Exception:
        return False


def _evaluate_cssbuy_pdp_stock_sync(item_page_url: str) -> CssbuyPdpStockProbe:
    pdp = cssbuy_playwright_pdp_url(item_page_url)
    if not pdp:
        return CssbuyPdpStockProbe(
            status="error",
            error="Không suy ra được URL CSSBuy goodsDetail để mở Playwright.",
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return CssbuyPdpStockProbe(
            status="error",
            error=f"Thiếu Playwright để mở CSSBuy: {exc}",
        )

    from app.core.config import settings

    ua = getattr(settings, "IMPORT_1688_USER_AGENT", None) or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    timeout_ms = _cssbuy_playwright_timeout_ms()
    headless = _cssbuy_playwright_headless()
    clicked = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(
                viewport={"width": 1366, "height": 1000},
                locale="en-US",
                timezone_id="Asia/Shanghai",
                user_agent=ua,
            )
            page = context.new_page()
            try:
                try:
                    from app.services.import_scraper_cookies import seed_playwright_context_cookies

                    seed_playwright_context_cookies(
                        context,
                        page,
                        prefer_hosts={"cssbuy.com"},
                        target_url=pdp,
                    )
                except Exception:
                    pass
                page.goto(pdp, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(20_000, timeout_ms))
                except Exception:
                    pass
                page.wait_for_timeout(1_800)

                html0 = ""
                try:
                    html0 = page.content() or ""
                except Exception:
                    html0 = ""
                title0 = ""
                try:
                    title0 = page.title() or ""
                except Exception:
                    title0 = ""
                if cssbuy_html_suggests_security_block(html0, title=title0, url=page.url or pdp):
                    return CssbuyPdpStockProbe(
                        status="blocked",
                        error=(
                            "CSSBuy bị Cloudflare / CAPTCHA / chặn bảo mật — fallback Vipomall/PandaMall."
                        )[:1000],
                    )

                clicked = _click_cssbuy_accept_risks(page)
                if clicked:
                    page.wait_for_timeout(1_200)
                    _click_cssbuy_accept_risks(page)
                    page.wait_for_timeout(800)
                try:
                    page.locator(".ty_button_btn6, .ty_button_btn1").first.wait_for(
                        state="visible", timeout=min(18_000, timeout_ms)
                    )
                except Exception:
                    try:
                        page.get_by_text("Add to Cart", exact=False).first.wait_for(
                            state="visible", timeout=4_000
                        )
                    except Exception:
                        pass
                page.wait_for_timeout(400)

                html1 = ""
                try:
                    html1 = page.content() or ""
                except Exception:
                    html1 = html0
                title1 = title0
                try:
                    title1 = page.title() or title0
                except Exception:
                    pass
                if cssbuy_html_suggests_security_block(html1, title=title1, url=page.url or pdp):
                    return CssbuyPdpStockProbe(
                        status="blocked",
                        error=(
                            "CSSBuy bị Cloudflare / CAPTCHA / chặn bảo mật — fallback Vipomall/PandaMall."
                        )[:1000],
                        clicked_accept_risks=clicked,
                    )

                snap = page.evaluate(_CSSBUY_PDP_PROBE_JS)
                if not isinstance(snap, dict):
                    return CssbuyPdpStockProbe(
                        status="error",
                        error="Playwright CSSBuy không đọc được DOM PDP.",
                        clicked_accept_risks=clicked,
                    )
                if snap.get("blocked"):
                    return CssbuyPdpStockProbe(
                        status="blocked",
                        error=(
                            "CSSBuy bị Cloudflare / CAPTCHA / chặn bảo mật — fallback Vipomall/PandaMall."
                        )[:1000],
                        clicked_accept_risks=clicked,
                    )
                found = bool(snap.get("addToCartFound"))
                looks = bool(snap.get("looksLikePdp"))
                st = classify_cssbuy_add_to_cart_cta(found=found)
                if st == "in_stock":
                    return CssbuyPdpStockProbe(
                        status="in_stock",
                        clicked_accept_risks=clicked,
                        add_to_cart_found=True,
                    )
                if not looks:
                    err = "CSSBuy: không mở được trang sản phẩm sau modal — coi hết hàng."
                else:
                    err = "CSSBuy: không thấy nút «Add to Cart» / «Buy now» — coi hết hàng."
                return CssbuyPdpStockProbe(
                    status="out_of_stock",
                    error=err[:1000],
                    clicked_accept_risks=clicked,
                    add_to_cart_found=False,
                )
            finally:
                for cleanup in (page.close, context.close, browser.close):
                    try:
                        cleanup()
                    except Exception:
                        pass
    except CssbuySecurityBlocked as exc:
        return CssbuyPdpStockProbe(status="blocked", error=str(exc)[:1000], clicked_accept_risks=clicked)
    except Exception as exc:
        detail = str(exc).strip() or repr(exc) or type(exc).__name__
        low = detail.lower()
        if any(n in low for n in ("captcha", "cloudflare", "cf-ray", "challenge", "access denied")):
            return CssbuyPdpStockProbe(
                status="blocked",
                error=("CSSBuy bị chặn bảo mật / CAPTCHA / Cloudflare — fallback nền khác. " + detail)[:1000],
                clicked_accept_risks=clicked,
            )
        if "Executable doesn't exist" in detail or "playwright install" in low:
            detail = (
                f"{detail} — Cài Chromium: cd backend && .venv/Scripts/python -m playwright install chromium"
            )
        return CssbuyPdpStockProbe(
            status="error",
            error=f"Lỗi Playwright/CSSBuy: {detail}"[:1000],
            clicked_accept_risks=clicked,
        )


def evaluate_cssbuy_pdp_stock(item_page_url: str) -> CssbuyPdpStockProbe:
    """
    Playwright: mở goodsDetail, bấm «I accept the risks», đọc Add to Cart / Buy now.
    Tải được nút → in_stock (kể cả disabled). blocked = Cloudflare/captcha (fallback nền khác).
    """
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    timeout_sec = max(30.0, (_cssbuy_playwright_timeout_ms() / 1000.0) + 45.0)
    return run_import_playwright_sync(
        lambda: _evaluate_cssbuy_pdp_stock_sync(item_page_url),
        timeout_sec=timeout_sec,
    )
