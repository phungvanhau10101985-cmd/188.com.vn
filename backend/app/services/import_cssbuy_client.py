"""
Đọc dữ liệu SP qua CSSBuy (item page).

Trang có modal «I accept the risks» nhưng dữ liệu lấy từ POST `/web/item` (JSON) sau khi có CSRF cookie —
không cần Playwright hay bấm nút modal.

HTML trang GET (cùng phiên) được dùng thêm để phát hiện PDP còn bán được không: nút «Add To Cart»
và (nếu có) đoạn disclaimer «I have read… terms of service…» nhưng không có nút giỏ — coi hết hàng.

URL chuẩn:
  • 1688 offer → ``https://www.cssbuy.com/item-1688-{offerId}.html``
  • Taobao/Tmall id → ``https://www.cssbuy.com/item-{itemId}.html``
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

from app.services.import_hibox_scraper import (
    extract_hibox_1688_offer_digits,
    normalize_product_import_url,
)

logger = logging.getLogger(__name__)

_CSSBUY_HOST_OK = re.compile(r"(?i)^(?:www\.)?cssbuy\.com$")


class ImportCssbuyError(RuntimeError):
    pass


def is_cssbuy_item_url(raw: str) -> bool:
    try:
        p = urlparse(normalize_product_import_url((raw or "").strip()))
        if not _CSSBUY_HOST_OK.match(p.hostname or ""):
            return False
        path = (p.path or "").lower()
        return "item-" in path and path.endswith(".html")
    except Exception:
        return False


def hibox_slug_to_cssbuy_item_url(slug: str) -> Optional[str]:
    """abb-922… → item-1688-922… ; chỉ số → item-{id}.html"""
    s = (slug or "").strip()
    if not s or s == "hibox_import":
        return None
    oid = extract_hibox_1688_offer_digits(s)
    if oid:
        return f"https://www.cssbuy.com/item-1688-{oid}.html"
    if s.isdigit():
        return f"https://www.cssbuy.com/item-{s}.html"
    return None


def cssbuy_item_page_to_hibox_slug(item_page_url: str) -> Optional[str]:
    """Dùng lại `_find_products_for_hibox_slug` (khớp abb-* / id Taobao)."""
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

    slug = cssbuy_item_page_to_hibox_slug(url)
    if not slug:
        raise ImportCssbuyError("Không trích được itemId từ URL CSSBuy.")
    oid1688 = extract_hibox_1688_offer_digits(slug)
    if oid1688:
        typ = "1688"
        digits = oid1688
    elif slug.isdigit():
        typ = "taobao"
        digits = slug
    else:
        raise ImportCssbuyError(f"Slug Hibox không map được sang CSSBuy API: {slug!r}")

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
