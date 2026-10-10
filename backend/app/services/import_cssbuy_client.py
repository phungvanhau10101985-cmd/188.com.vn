"""
Đọc dữ liệu SP qua CSSBuy.

Import catalog: GET trang ``item-*.html`` + POST ``/web/item`` (CSRF cookie).

Kiểm tra tồn nguồn: Playwright mở PDP SPA ``/shop/goodsDetail?type=&id=``, bấm
«I accept the risks», rồi bấm «Add to Cart». Có nút chưa đủ để coi còn hàng —
nhãn / toast sau cú bấm (Out of stock, 下架, hết hàng, …) mới là hết hàng.

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


_CSSBUY_OOS_NOTICE_RES = (
    re.compile(r"\bout of stock\b", re.I),
    re.compile(r"\bsold\s*out\b", re.I),
    re.compile(r"\bno longer (?:available|for sale)\b", re.I),
    re.compile(r"\b(?:has been removed|been taken down|has been discontinued|item removed|product removed)\b", re.I),
    re.compile(r"\boff the shelf\b", re.I),
    re.compile(r"\b(?:item|product|goods)\b[^.\n]{0,48}\b(?:does not exist|do not exist|unavailable|not available)\b", re.I),
    re.compile(r"\b(?:cannot|can't) be purchased\b", re.I),
    re.compile(r"下架|缺货|无货|售罄|库存不足|宝贝不存在|商品不存在|已售完"),
    re.compile(r"hết hàng|het hang|ngừng bán|ngung ban|tạm hết|tam het|ngừng kinh doanh|ngung kinh doanh", re.I),
    re.compile(r"không tìm thấy thông tin sản phẩm", re.I),
)


def visible_text_out_of_stock_notice(text: str) -> Optional[str]:
    """Câu ngắn trong vùng giá / hộp thông báo. Không dùng cho cả chân trang hay mô tả."""
    blob = re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()
    if not blob:
        return None
    for pat in _CSSBUY_OOS_NOTICE_RES:
        match = pat.search(blob)
        if match:
            return re.sub(r"\s+", " ", match.group(0)).strip()[:180]
    return None


_STOCK_ZONE_JS = r"""() => {
  const textOf = (el) => ((el && (el.innerText || el.textContent)) || "").replace(/\s+/g, " ").trim();
  const bits = [];
  const pushShort = (el) => {
    const t = textOf(el);
    if (t && t.length <= 120) bits.push(t);
  };
  document.querySelectorAll(
    ".el-message,.el-message-box,.el-notification,.ant-message,.ant-message-notice,.toast,[role='alert'],.swal2-popup"
  ).forEach(pushShort);
  const zone = document.querySelector(
    ".shop_right, .shop_info, .product-price, .main-price, .group-btn, .list-btn, .product-type-content"
  );
  if (zone) zone.querySelectorAll("span, p, div, button, label").forEach(pushShort);
  const risksOpen = Array.from(document.querySelectorAll("button, div, span, p")).some((el) => {
    return /^i accept the risks$/i.test(textOf(el)) && el.offsetParent !== null;
  });
  const productImage = Array.from(document.querySelectorAll("img")).some((img) =>
    /alicdn|cbu01|ibank/i.test(img.currentSrc || img.src || "")
  );
  const titleEl = document.querySelector("h1, .product-name, .product-title, .goods-name, .goods_name");
  const title = textOf(titleEl).slice(0, 180);
  const main = document.querySelector("main") || document.body;
  const missingProduct = /không tìm thấy thông tin sản phẩm/i.test(textOf(main).slice(0, 2500));
  return { zoneText: bits.join("\n").slice(0, 4000), risksOpen, productImage, title, missingProduct };
}"""


def read_page_stock_zone(page: Any) -> Dict[str, Any]:
    """Vùng giá, nút mua và toast. Không gồm chân trang."""
    try:
        data = page.evaluate(_STOCK_ZONE_JS)
    except Exception:
        data = None
    if not isinstance(data, dict):
        return {"zoneText": "", "risksOpen": False, "productImage": False, "title": "", "missingProduct": False}
    return {
        "zoneText": str(data.get("zoneText") or ""),
        "risksOpen": bool(data.get("risksOpen")),
        "productImage": bool(data.get("productImage")),
        "title": str(data.get("title") or ""),
        "missingProduct": bool(data.get("missingProduct")),
    }


def notice_from_stock_zone(zone: Dict[str, Any]) -> Optional[str]:
    if zone.get("missingProduct"):
        return "Không tìm thấy thông tin sản phẩm"
    return visible_text_out_of_stock_notice(str(zone.get("zoneText") or ""))


def product_zone_looks_loaded(zone: Dict[str, Any]) -> bool:
    """Ảnh nguồn hoặc tên sản phẩm đã hiện — trang không còn là vỏ trống."""
    if zone.get("risksOpen"):
        return False
    if zone.get("productImage"):
        return True
    title = re.sub(r"\s+", " ", str(zone.get("title") or "")).strip()
    if len(title) < 8:
        return False
    generic = title.lower()
    if generic.startswith("cssbuy") or "panda" in generic or generic.startswith("vipo"):
        return False
    return True


def classify_cssbuy_add_to_cart_cta(
    *,
    found: bool,
    disabled: bool = False,
    looks_like_pdp: bool = False,
    out_of_stock_notice: str = "",
) -> str:
    """Có nút giỏ chưa đủ. Nhãn hết hàng sau cú bấm thắng hơn nút; không có nút → hết hàng."""
    _ = (disabled, looks_like_pdp)
    if (out_of_stock_notice or "").strip():
        return "out_of_stock"
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


def poll_page_out_of_stock_notice(page: Any, *, rounds: int = 4, pause_ms: int = 700) -> Optional[str]:
    """Đọc vùng giá / toast vài nhịp — nhãn hết hàng có thể hiện trễ sau cú bấm giỏ."""
    notice = notice_from_stock_zone(read_page_stock_zone(page))
    if notice:
        return notice
    for _ in range(max(1, rounds)):
        try:
            page.wait_for_timeout(pause_ms)
        except Exception:
            return notice
        notice = notice_from_stock_zone(read_page_stock_zone(page))
        if notice:
            return notice
    return None


def _cssbuy_page_visible_text(page: Any) -> str:
    try:
        text = page.evaluate("() => (document.body && document.body.innerText) || ''")
    except Exception:
        return ""
    return text if isinstance(text, str) else ""


def _dismiss_cssbuy_human_verification(page: Any) -> bool:
    """Đóng modal «Please complete the human verification first» nếu nó che nút giỏ."""
    try:
        closed = page.evaluate(
            """() => {
              const nodes = Array.from(document.querySelectorAll("div,button,span,i"));
              const box = nodes.find((el) =>
                /please complete the human verification first/i.test((el.innerText || "") + "")
              );
              if (!box) return false;
              const scope = box.parentElement || document;
              const closer = Array.from(scope.querySelectorAll("div,button,span,i")).find((el) => {
                const t = ((el.innerText || "") + "").trim();
                const c = String(el.className || "");
                return t === "×" || t === "x" || /close|el-dialog__close|icon-close/i.test(c);
              });
              if (!closer) return false;
              closer.click();
              return true;
            }"""
        )
        return bool(closed)
    except Exception:
        return False


def _click_cssbuy_add_to_cart(page: Any) -> str:
    try:
        loc = page.locator(".ty_button_btn6").first
        if loc.count() == 0:
            loc = page.get_by_text("Add to Cart", exact=False).first
        loc.click(timeout=8_000, force=True)
        return "clicked"
    except Exception as exc:
        return f"fail: {exc}"[:240]


def _probe_cssbuy_cart_click(page: Any) -> Tuple[Optional[str], str, bool]:
    """
    Bấm Add to Cart rồi đọc nhãn/toast. Không bấm Buy now.

    Trả (notice, click_note, verification_blocked). verification_blocked khi cú bấm
    không tới nút và modal «human verification» vẫn che trang — không kết luận còn hàng.
    """
    _dismiss_cssbuy_human_verification(page)
    page.wait_for_timeout(400)
    already = notice_from_stock_zone(read_page_stock_zone(page))
    if already:
        return already, "already-visible", False
    click_note = _click_cssbuy_add_to_cart(page)
    notice = poll_page_out_of_stock_notice(page)
    text = _cssbuy_page_visible_text(page)
    verification_blocked = (not notice) and click_note.startswith("fail:") and ("human verification" in text.lower())
    return notice, click_note, verification_blocked


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
                notice: Optional[str] = None
                click_note = ""
                if found:
                    notice, click_note, verification_blocked = _probe_cssbuy_cart_click(page)
                    if notice:
                        pass
                    elif verification_blocked:
                        return CssbuyPdpStockProbe(
                            status="blocked",
                            error=(
                                "CSSBuy: modal «human verification» che nút giỏ, bấm không tới — "
                                "các nền khác vẫn được đọc."
                            )[:1000],
                            clicked_accept_risks=clicked,
                            add_to_cart_found=True,
                        )
                    elif click_note.startswith("fail"):
                        return CssbuyPdpStockProbe(
                            status="error",
                            error="CSSBuy: thấy nút giỏ nhưng bấm không tới — chưa kết luận còn hàng."[:1000],
                            clicked_accept_risks=clicked,
                            add_to_cart_found=True,
                        )
                else:
                    zone = read_page_stock_zone(page)
                    if zone.get("risksOpen"):
                        return CssbuyPdpStockProbe(
                            status="error",
                            error="CSSBuy: modal «I accept the risks» còn mở — trang chưa đọc được, chưa kết luận hết hàng.",
                            clicked_accept_risks=clicked,
                            add_to_cart_found=False,
                        )
                    notice = notice_from_stock_zone(zone)
                    if not notice and not product_zone_looks_loaded(zone):
                        return CssbuyPdpStockProbe(
                            status="error",
                            error="CSSBuy: chưa hiện giá, tên hoặc ảnh sản phẩm — chưa kết luận hết hàng.",
                            clicked_accept_risks=clicked,
                            add_to_cart_found=False,
                        )
                st = classify_cssbuy_add_to_cart_cta(found=found, out_of_stock_notice=notice or "")
                if st == "in_stock":
                    return CssbuyPdpStockProbe(
                        status="in_stock",
                        clicked_accept_risks=clicked,
                        add_to_cart_found=True,
                    )
                if notice:
                    err = f"CSSBuy: vùng giá/thông báo báo hết hàng («{notice}»)."
                elif looks or product_zone_looks_loaded(read_page_stock_zone(page)):
                    err = "CSSBuy: trang sản phẩm đã hiện nhưng không thấy nút «Add to Cart» / «Buy now» — coi hết hàng."
                else:
                    return CssbuyPdpStockProbe(
                        status="error",
                        error="CSSBuy: chưa hiện giá, tên hoặc ảnh sản phẩm — chưa kết luận hết hàng.",
                        clicked_accept_risks=clicked,
                        add_to_cart_found=False,
                    )
                return CssbuyPdpStockProbe(
                    status="out_of_stock",
                    error=err[:1000],
                    clicked_accept_risks=clicked,
                    add_to_cart_found=found,
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
    Playwright: mở goodsDetail, bấm «I accept the risks», rồi bấm «Add to Cart».
    Nhãn hết hàng sau cú bấm → out_of_stock dù nút vẫn còn. Không bấm được vì modal
    human verification → blocked (fallback nền khác). Không thấy nút → out_of_stock.
    """
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    timeout_sec = max(30.0, (_cssbuy_playwright_timeout_ms() / 1000.0) + 45.0)
    return run_import_playwright_sync(
        lambda: _evaluate_cssbuy_pdp_stock_sync(item_page_url),
        timeout_sec=timeout_sec,
    )
