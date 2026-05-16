from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import or_

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.import_1688_scraper import (
    _load_cookie_json,
    _normalize_playwright_cookie,
    canonical_1688_offer_pc_url,
    extract_1688_numeric_offer_id,
)

logger = logging.getLogger(__name__)

_queue: deque[int] = deque()
_queued_ids: set[int] = set()
_queue_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()

_OUT_OF_STOCK_PATTERNS = (
    "商品已下架",
    "该商品已下架",
    "商品不存在",
    "该商品不存在",
    "宝贝不存在",
    "已售罄",
    "售罄",
    "暂无现货",
    "暂时缺货",
    "库存不足",
    "找不到商品",
)

_IN_STOCK_PATTERNS = (
    "立即订购",
    "加入进货单",
    "加入采购单",
    "立即购买",
    "起批量",
    "库存",
)


def _format_source_blocked_detail(summary: str, title: str, text: str, href: str) -> str:
    """Ghép tiêu đề + URL + đoạn DOM để admin thấy phía nguồn báo gì."""
    t_one = " ".join(str(text).split())
    excerpt = t_one[:720]
    lines = [
        "[1688 — phản hồi trang khi kiểm tra] " + summary.strip(),
        "Tiêu đề trình duyệt: " + (title or "").strip()[:280],
        "URL hiện tại: " + (href or "").strip()[:500],
    ]
    if excerpt:
        lines.append("Trích nội dung hiển thị (rút gọn): " + excerpt)
    return "\n".join(lines)[:2400]


def _blocked_probe_from_dom(title: str, text: str, href: str) -> Optional[SourceStockCheckResult]:
    """Captcha / đăng nhập / giới hạn / ‘phát hiện quét’ — không tiếp tục queue tự động phía frontend."""
    hay = f"{title}\n{text}"
    probes: List[Tuple[re.Pattern[str], str]] = [
        (
            re.compile(
                r"验证码|滑块验证|拖动滑块|向右滑动|安全验证|人机验证|身份验证|验证您的身份",
                re.I,
            ),
            "Trang đang hiển thị captcha hoặc bước xác minh an toàn.",
        ),
        (
            re.compile(r"请登录|请先登录|登录后查看|账号登录|登录\s*1688", re.I),
            "Trang yêu cầu đăng nhập tài khoản.",
        ),
        (
            re.compile(
                r"访问被拒绝|访问过于频繁|访问请求过于频繁|您的访问过于频繁|请求太过频繁|访问过快",
                re.I,
            ),
            "Trang báo giới hạn lượt truy cập hoặc từ chối kết nối.",
        ),
        (
            re.compile(
                r"风控|风险控制|系统检测.*异常|非正常访问|疑似爬虫|自动化访问|恶意访问|拦截访问",
                re.I,
            ),
            "Trang báo kiểm soát rủi ro / nghi ngờ truy cập tự động hoặc quét dữ liệu.",
        ),
        (
            re.compile(
                r"sorry[, ]+you\s+have\s+been\s+blocked|access\s+denied|403\s*forbidden|\bforbidden\b",
                re.I,
            ),
            "Trang báo chặn truy cập (tiếng Anh / forbidden).",
        ),
    ]
    for rx, summary in probes:
        if rx.search(hay):
            return SourceStockCheckResult(
                status="blocked",
                error=_format_source_blocked_detail(summary, title, text, href),
            )
    return None


@dataclass
class SourceStockCheckResult:
    status: str
    error: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _source_url(product: Product) -> str:
    url = (product.link_default or "").strip()
    offer_id = extract_1688_numeric_offer_id(url)
    if offer_id:
        return canonical_1688_offer_pc_url(offer_id) or url
    return url


def _is_supported_1688_product(product: Product) -> bool:
    return bool(extract_1688_numeric_offer_id(product.link_default or ""))


def _datetime_is_recent(value: Optional[datetime], seconds: int) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > _utcnow() - timedelta(seconds=seconds)


def product_stock_cache_is_stale(product: Product) -> bool:
    checked_at = product.source_stock_checked_at
    if checked_at is None:
        return True
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return checked_at <= _utcnow() - timedelta(minutes=settings.SOURCE_STOCK_CHECK_STALE_MINUTES)


def enqueue_source_stock_check(product_id: int, *, reason: str = "manual", force: bool = False) -> bool:
    """Đưa sản phẩm vào queue in-process. Trả False nếu bị bỏ qua hoặc đã có trong queue."""
    if not getattr(settings, "SOURCE_STOCK_CHECK_ENABLED", True) and not force:
        return False

    with _queue_lock:
        if product_id in _queued_ids:
            return False
        _queued_ids.add(product_id)
        _queue.append(product_id)

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or not _is_supported_1688_product(product):
            with _queue_lock:
                _queued_ids.discard(product_id)
                try:
                    _queue.remove(product_id)
                except ValueError:
                    pass
            return False
        product.source_stock_status = "queued"
        product.source_stock_error = None
        product.source_stock_next_check_at = _utcnow()
        db.commit()
        logger.info("source stock check queued: product_id=%s reason=%s", product_id, reason)
        return True
    except Exception as exc:
        db.rollback()
        logger.warning("source stock enqueue failed: product_id=%s reason=%s error=%s", product_id, reason, exc)
        return False
    finally:
        db.close()


def enqueue_product_view_stock_check_if_needed(product: Product) -> bool:
    """Gọi khi khách mở PDP: chỉ enqueue nếu cache thiếu/cũ và không spam cùng một sản phẩm."""
    if not product or not _is_supported_1688_product(product):
        return False
    status = (product.source_stock_status or "").strip().lower()
    if status in {"queued", "checking"} and _datetime_is_recent(
        product.source_stock_next_check_at or product.source_stock_checked_at,
        settings.SOURCE_STOCK_CHECK_PAGEVIEW_MIN_INTERVAL_SECONDS,
    ):
        return False
    if not product_stock_cache_is_stale(product):
        return False
    return enqueue_source_stock_check(product.id, reason="product_view")


def _pop_queued_id() -> Optional[int]:
    with _queue_lock:
        if not _queue:
            return None
        product_id = _queue.popleft()
        _queued_ids.discard(product_id)
        return product_id


def _claim_due_product_id() -> Optional[int]:
    db = SessionLocal()
    try:
        now = _utcnow()
        stale_cutoff = now - timedelta(minutes=settings.SOURCE_STOCK_CHECK_STALE_MINUTES)
        product = (
            db.query(Product)
            .filter(Product.is_active == True)  # noqa: E712
            .filter(Product.link_default.isnot(None))
            .filter(Product.link_default.ilike("%1688.com%"))
            .filter(
                or_(
                    Product.source_stock_next_check_at.is_(None),
                    Product.source_stock_next_check_at <= now,
                    Product.source_stock_checked_at.is_(None),
                    Product.source_stock_checked_at <= stale_cutoff,
                )
            )
            .order_by(Product.source_stock_next_check_at.isnot(None), Product.source_stock_next_check_at.asc(), Product.id.asc())
            .first()
        )
        if not product or not _is_supported_1688_product(product):
            return None
        product.source_stock_status = "queued"
        product.source_stock_next_check_at = now
        db.commit()
        return product.id
    except Exception as exc:
        db.rollback()
        logger.warning("source stock claim due product failed: %s", exc)
        return None
    finally:
        db.close()


def _evaluate_page_stock(url: str) -> SourceStockCheckResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return SourceStockCheckResult(
            status="error",
            error="Backend chưa cài Playwright. Chạy pip install -r requirements.txt và playwright install chromium.",
        )

    cookies = _load_cookie_json()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.SOURCE_STOCK_CHECK_HEADLESS)
            context = browser.new_context(
                user_agent=settings.IMPORT_1688_USER_AGENT,
                viewport={"width": 1366, "height": 900},
                locale="zh-CN",
            )
            if cookies:
                context.add_cookies([_normalize_playwright_cookie(c) for c in cookies])
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=settings.SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=min(12000, settings.SOURCE_STOCK_CHECK_PLAYWRIGHT_TIMEOUT_MS))
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(1200)
                payload = page.evaluate(
                    """() => {
                      const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').slice(0, 20000);
                      return { title: document.title || '', text, href: location.href };
                    }"""
                )
            finally:
                for _cleanup in (
                    lambda: page.close(),
                    lambda: context.close(),
                    lambda: browser.close(),
                ):
                    try:
                        _cleanup()
                    except Exception:
                        pass
    except Exception as exc:
        return SourceStockCheckResult(status="error", error=str(exc)[:1000])

    title = str((payload or {}).get("title") or "")
    text = str((payload or {}).get("text") or "")
    href = str((payload or {}).get("href") or "")

    blocked = _blocked_probe_from_dom(title, text, href)
    if blocked is not None:
        return blocked

    haystack = f"{title} {text}"
    if any(token in haystack for token in _OUT_OF_STOCK_PATTERNS):
        return SourceStockCheckResult(status="out_of_stock")
    if "1688.com/offer/" not in href and "detail.1688.com" not in href:
        return SourceStockCheckResult(status="error", error=f"1688 chuyển hướng ngoài trang chi tiết: {href[:300]}")
    if any(token in haystack for token in _IN_STOCK_PATTERNS):
        return SourceStockCheckResult(status="in_stock")
    return SourceStockCheckResult(status="unknown", error="Không nhận diện được trạng thái tồn kho từ DOM 1688.")


def check_product_source_stock(product_id: int) -> Optional[SourceStockCheckResult]:
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or not _is_supported_1688_product(product):
            return None
        previous_status = (product.source_stock_status or "").strip().lower()
        product.source_stock_status = "checking"
        product.source_stock_error = None
        product.source_stock_next_check_at = _utcnow()
        db.commit()

        result = _evaluate_page_stock(_source_url(product))
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return result
        now = _utcnow()
        product.source_stock_status = result.status
        product.source_stock_checked_at = now
        product.source_stock_error = result.error
        retry_minutes = (
            settings.SOURCE_STOCK_CHECK_ERROR_RETRY_MINUTES
            if result.status in {"error", "unknown", "blocked"}
            else settings.SOURCE_STOCK_CHECK_STALE_MINUTES
        )
        product.source_stock_next_check_at = now + timedelta(minutes=retry_minutes)
        if result.status == "out_of_stock":
            product.available = 0
        elif result.status == "in_stock" and (product.available or 0) <= 0 and previous_status == "out_of_stock":
            product.available = 500
        db.commit()
        if result.status in {"error", "unknown", "blocked"}:
            logger.warning("source stock check issue: product_id=%s status=%s error=%s", product_id, result.status, result.error)
        else:
            logger.info("source stock checked: product_id=%s status=%s", product_id, result.status)
        return result
    except Exception as exc:
        db.rollback()
        logger.exception("source stock check failed: product_id=%s", product_id)
        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if product:
                now = _utcnow()
                product.source_stock_status = "error"
                product.source_stock_checked_at = now
                product.source_stock_error = str(exc)[:1000]
                product.source_stock_next_check_at = now + timedelta(minutes=settings.SOURCE_STOCK_CHECK_ERROR_RETRY_MINUTES)
                db.commit()
        except Exception:
            db.rollback()
        return SourceStockCheckResult(status="error", error=str(exc)[:1000])
    finally:
        db.close()


def _worker_loop() -> None:
    logger.info(
        "source stock checker started: interval=%ss stale=%sm",
        settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS,
        settings.SOURCE_STOCK_CHECK_STALE_MINUTES,
    )
    while True:
        product_id = _pop_queued_id() or _claim_due_product_id()
        if product_id is None:
            time.sleep(min(15, settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS))
            continue
        check_product_source_stock(product_id)
        time.sleep(settings.SOURCE_STOCK_CHECK_INTERVAL_SECONDS)


def start_source_stock_checker_daemon_if_enabled() -> None:
    if not getattr(settings, "SOURCE_STOCK_CHECK_ENABLED", True):
        return
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(target=_worker_loop, name="source-stock-checker", daemon=True)
        thread.start()
