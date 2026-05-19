"""
Fallback kiểm tra tồn nguồn qua PDP Vipomall (gương 1688).

Chỉ áp dụng khi đã suy ra được offerId 1688 (link offer/Hibox abb-*/CSSBuy item-1688 hoặc mã A{offer}a188…).
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
from app.services.import_cssbuy_client import cssbuy_item_page_to_hibox_slug, is_cssbuy_item_url
from app.services.import_hibox_scraper import (
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    normalize_product_import_url,
)

logger = logging.getLogger(__name__)

_VIPOMALL_HOST_OK = re.compile(r"^(?:www\.)?vipomall\.vn$", re.I)
_PRODUCT_ID_A_OFFER_RE = re.compile(r"^A(\d+)a188", re.I)

_BLOCK_MARKERS = (
    "captcha",
    "验证码",
    "cf-ray",
    "cloudflare",
    "attention required",
    "access denied",
    "blocked",
    "forbidden",
    "rate limit",
)


def build_vipomall_1688_pdp_url(offer_id: str) -> str:
    oid = str(offer_id or "").strip()
    return f"https://vipomall.vn/san-pham/{oid}?platform_type=10" if oid.isdigit() else ""


def resolve_numeric_1688_offer_id_from_source_url(
    url: str,
    *,
    fallback_product_id: Optional[str] = None,
) -> Optional[str]:
    """
    offerId thuần số từ URL nguồn (1688 / Hibox abb-* / cssbuy item-1688) hoặc từ product_id dạng A{offer}a188….
    Taobao/Tmall thuần (slug số, link item.taobao…) → None (không có PDP 1688 trên Vipomall theo offer).
    """
    norm = (normalize_product_import_url((url or "").strip()) or (url or "").strip()).strip()
    oid_url = extract_offer_id(norm)
    if oid_url and oid_url.isdigit():
        return oid_url
    slug = extract_hibox_slug(norm)
    if slug:
        abb = extract_hibox_1688_offer_digits(slug)
        if abb:
            return abb
    if is_cssbuy_item_url(norm):
        cs_slug = cssbuy_item_page_to_hibox_slug(norm)
        if cs_slug:
            abb = extract_hibox_1688_offer_digits(cs_slug)
            if abb:
                return abb
    raw_pid = (fallback_product_id or "").strip()
    m = _PRODUCT_ID_A_OFFER_RE.match(raw_pid)
    if m:
        return m.group(1)
    return None


def vipomall_html_suggests_blocked(html: str) -> bool:
    blob = re.sub(r"\s+", " ", (html or "").strip()[:120_000].lower())
    if len(blob) < 80:
        return True
    return any(marker in blob for marker in _BLOCK_MARKERS)


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
    if "add-cart" in low and ("cart_detail.svg" in low or "giỏ hàng" in low):
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


def evaluate_vipomall_1688_offer_stock(offer_id: str) -> Tuple[str, Optional[str], str]:
    """
    Trả (status, error, checked_via) với status in {in_stock, out_of_stock, blocked, error}.
    """
    url = build_vipomall_1688_pdp_url(offer_id)
    if not url:
        return "error", "Không có offerId 1688 hợp lệ để kiểm tra Vipomall.", "vipomall"
    html, err = fetch_vipomall_pdp_html(url)
    if err:
        return "error", f"Vipomall: không tải được PDP ({err}).", "vipomall"
    if vipomall_html_suggests_blocked(html):
        return (
            "blocked",
            "Vipomall: phản hồi giống trang chặn/CAPTCHA hoặc HTML quá ngắn — chưa đọc được PDP.",
            "vipomall",
        )
    if vipomall_html_shows_add_to_cart_cta(html):
        return "in_stock", None, "vipomall"
    return (
        "out_of_stock",
        "Vipomall: không thấy nút/chữ «Thêm giỏ hàng» trên PDP — coi hết hàng nguồn (1688).",
        "vipomall",
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
    from app.services.admin_source_stock_batch import _find_products_for_hibox_slug
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
            "detail": "Không suy ra được offerId 1688 — không thể kiểm tra qua Vipomall (chỉ hỗ trợ link 1688 / Hibox abb-* / CSSBuy item-1688 hoặc mã A{offer}a188…).",
            "warnings": [],
            "matched_orm": [],
        }

    vm_url = build_vipomall_1688_pdp_url(oid)
    matched: List[Any] = list(_find_products_for_hibox_slug(db, f"abb-{oid}"))
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
