"""Kiểm tra tồn nguồn PandaMall: nút «Thêm vào giỏ» / «Mua ngay» (kể cả disabled)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.services.import_pandamall_scraper import (
    ImportPandamallError,
    resolve_pandamall_import_url,
    try_pandamall_playwright_auto_login,
)
from app.services.import_source_ids import normalize_product_import_url

logger = logging.getLogger(__name__)

_PANDAMALL_PDP_PROBE_JS = """() => {
  const html = document.documentElement ? document.documentElement.outerHTML : "";
  const low = (html || "").toLowerCase();
  const title = document.title || "";
  const bodyText = (document.body && document.body.innerText) || "";
  const pdpOk = ["btn-addcart", "btn-buynow", "thêm vào giỏ", "mua ngay", "group-btn"].some(
    (m) => low.includes(m) || bodyText.toLowerCase().includes(m)
  );
  const challenge = ["just a moment", "attention required", "cf-browser-verification", "verify you are human"].some(
    (n) => title.toLowerCase().includes(n) || low.includes(n)
  );
  const add = document.querySelector(".group-btn .btn-addcart, button.btn-addcart");
  const buy = document.querySelector(".group-btn .btn-buynow, button.btn-buynow");
  const addByText = Array.from(document.querySelectorAll("button, span")).find((el) =>
    /^thêm vào giỏ$/i.test(((el.innerText || "") + "").trim())
  );
  const buyByText = Array.from(document.querySelectorAll("button, span")).find((el) =>
    /^mua ngay$/i.test(((el.innerText || "") + "").trim())
  );
  const login = /đăng nhập/i.test(bodyText) && (location.href || "").toLowerCase().includes("login");
  return {
    blocked: !pdpOk && challenge,
    login: !!login,
    ctaFound: !!(add || buy || addByText || buyByText),
  };
}"""


def pandamall_html_shows_cart_or_buy_cta(html: str) -> bool:
    """Nút PandaMall: .btn-addcart «Thêm vào giỏ» hoặc .btn-buynow «Mua ngay» — disabled vẫn tính."""
    low = (html or "").lower()
    if not low.strip():
        return False
    if "btn-addcart" in low or "btn-buynow" in low:
        return True
    if "thêm vào giỏ" in low or "them vao gio" in low:
        return True
    if "group-btn" in low and ("mua ngay" in low or "giỏ" in low):
        return True
    return False


def pandamall_html_suggests_blocked(html: str, *, title: str = "") -> bool:
    title_l = (title or "").lower()
    if "just a moment" in title_l or "attention required" in title_l:
        return True
    blob = re.sub(r"\s+", " ", (html or "")[:80_000].lower())
    if pandamall_html_shows_cart_or_buy_cta(blob):
        return False
    return any(
        n in blob
        for n in (
            "just a moment",
            "cf-browser-verification",
            "verify you are human",
            "captcha",
            "验证码",
        )
    )


def _evaluate_pandamall_pdp_stock_sync(page_url: str) -> Tuple[str, Optional[str], str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return "error", f"Thiếu Playwright để mở PandaMall: {exc}", "pandamall"

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
                        context, page, prefer_hosts={"pandamall.vn"}, target_url=page_url
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
                title0 = ""
                try:
                    title0 = page.title() or ""
                except Exception:
                    pass
                if pandamall_html_suggests_blocked(html0, title=title0):
                    return (
                        "blocked",
                        "PandaMall bị Cloudflare / CAPTCHA — dừng nếu các nền khác cũng bị chặn.",
                        "pandamall",
                    )
                try:
                    try_pandamall_playwright_auto_login(page, page_url)
                    page.wait_for_timeout(1_200)
                except Exception:
                    pass
                try:
                    page.locator(".btn-addcart, .btn-buynow, .group-btn").first.wait_for(
                        state="visible", timeout=min(18_000, timeout_ms)
                    )
                except Exception:
                    pass
                snap = page.evaluate(_PANDAMALL_PDP_PROBE_JS)
                html1 = page.content() or html0
                if isinstance(snap, dict) and snap.get("blocked"):
                    return (
                        "blocked",
                        "PandaMall bị Cloudflare / CAPTCHA — dừng nếu các nền khác cũng bị chặn.",
                        "pandamall",
                    )
                if isinstance(snap, dict) and snap.get("login") and not snap.get("ctaFound"):
                    from app.services.import_scraper_cookies import get_pandamall_account

                    acc = get_pandamall_account()
                    has_acc = bool(str(acc.get("username") or "").strip() and str(acc.get("password") or "").strip())
                    msg = (
                        "PandaMall yêu cầu đăng nhập — chưa đọc được nút giỏ/mua."
                        if has_acc
                        else "PandaMall yêu cầu đăng nhập — chưa có tài khoản (pandamall-account.json)."
                    )
                    return ("error", msg, "pandamall")
                if (isinstance(snap, dict) and snap.get("ctaFound")) or pandamall_html_shows_cart_or_buy_cta(html1):
                    return "in_stock", None, "pandamall"
                return (
                    "out_of_stock",
                    "PandaMall: không thấy nút «Thêm vào giỏ» / «Mua ngay» — coi hết hàng.",
                    "pandamall",
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
                ("PandaMall bị chặn bảo mật / CAPTCHA / Cloudflare. " + detail)[:1000],
                "pandamall",
            )
        return "error", f"Lỗi Playwright/PandaMall: {detail}"[:1000], "pandamall"


def evaluate_pandamall_source_stock(raw_url: str) -> Tuple[str, Optional[str], str]:
    """Playwright: .btn-addcart / .btn-buynow tải được → còn hàng, kể cả disabled."""
    try:
        page_url, _plat = resolve_pandamall_import_url((raw_url or "").strip())
    except ImportPandamallError as exc:
        return "error", f"Không quy đổi được sang PandaMall: {exc}"[:1000], "pandamall"
    if not page_url:
        return "error", "Không có URL PandaMall hợp lệ.", "pandamall"
    from app.services.import_playwright_dispatch import run_import_playwright_sync

    timeout_sec = max(
        30.0,
        (int(getattr(settings, "SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS", 90_000) or 90_000) / 1000.0) + 45.0,
    )
    return run_import_playwright_sync(
        lambda: _evaluate_pandamall_pdp_stock_sync(page_url),
        timeout_sec=timeout_sec,
    )


def pandamall_gather_admin_batch_scan(db: Any, *, seed_url: str) -> Dict[str, Any]:
    from app.services.admin_source_stock_batch import _find_products_for_item_slug
    from app.services.import_cssbuy_client import cssbuy_item_page_to_item_slug
    from app.services.vipomall_source_stock import resolve_numeric_1688_offer_id_from_source_url

    canonical_url = (normalize_product_import_url((seed_url or "").strip()) or (seed_url or "").strip()).strip()
    try:
        page_url, _plat = resolve_pandamall_import_url(canonical_url)
    except ImportPandamallError as exc:
        return {
            "canonical_url": canonical_url,
            "domain": "pandamall",
            "raw_status": "bad_url",
            "classified_out_of_stock": False,
            "detail": str(exc)[:1000],
            "warnings": [],
            "matched_orm": [],
        }
    oid = resolve_numeric_1688_offer_id_from_source_url(canonical_url)
    slug = f"abb-{oid}" if oid else (cssbuy_item_page_to_item_slug(canonical_url) or "")
    matched = list(_find_products_for_item_slug(db, slug)) if slug else []
    st, err, _via = evaluate_pandamall_source_stock(canonical_url)
    if st == "in_stock":
        return {
            "canonical_url": page_url,
            "domain": "pandamall",
            "raw_status": "ok",
            "classified_out_of_stock": False,
            "detail": None,
            "warnings": [],
            "matched_orm": matched,
        }
    if st == "out_of_stock":
        return {
            "canonical_url": page_url,
            "domain": "pandamall",
            "raw_status": "no_data",
            "classified_out_of_stock": True,
            "detail": err,
            "warnings": [],
            "matched_orm": matched,
        }
    if st == "blocked":
        return {
            "canonical_url": page_url,
            "domain": "pandamall",
            "raw_status": "blocked",
            "classified_out_of_stock": False,
            "detail": err,
            "warnings": [],
            "matched_orm": matched,
        }
    return {
        "canonical_url": page_url,
        "domain": "pandamall",
        "raw_status": "fetch_error",
        "classified_out_of_stock": False,
        "detail": err,
        "warnings": [],
        "matched_orm": matched,
    }
