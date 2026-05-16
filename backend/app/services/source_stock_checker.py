from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import or_

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.admin_source_stock_batch import _hibox_row_shows_color_size_catalog
from app.services.import_batch_url_coercion import FETCH_TARGET_HIBOX, coerce_url_for_excel_batch_import
from app.services.import_hibox_scraper import (
    ImportHiboxError,
    hibox_canonical_scrape_url,
    normalize_product_import_url,
    scrape_hibox_for_import,
)

logger = logging.getLogger(__name__)

_queue: deque[int] = deque()
_queued_ids: set[int] = set()
_queue_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()

@dataclass
class SourceStockCheckResult:
    status: str
    error: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _link_eligible_for_hibox_stock_check(url: str) -> bool:
    u = (url or "").strip().lower()
    if len(u) < 12:
        return False
    return any(
        marker in u
        for marker in (
            "hibox.mn",
            "taobao1688.kz",
            "1688.com",
            "offer.1688",
            "detail.1688",
            "taobao.com",
            "tmall.com",
        )
    )


def _evaluate_stock_via_hibox(raw_url: str) -> SourceStockCheckResult:
    """Đọc tình trạng qua scrape Hibox (quy đổi URL nguồn như luồng nhập Excel)."""
    canonical_url = (normalize_product_import_url((raw_url or "").strip()) or (raw_url or "").strip()).strip()
    hibox_url, coercion_err = coerce_url_for_excel_batch_import(canonical_url, FETCH_TARGET_HIBOX)
    if coercion_err:
        return SourceStockCheckResult(
            status="error",
            error=f"Không quy đổi được sang link Hibox hợp lệ: {coercion_err}"[:1000],
        )
    coerced = (hibox_url or "").strip()
    canonical_url = hibox_canonical_scrape_url(coerced) if coerced else canonical_url
    try:
        _raw_row, product_data, warns = scrape_hibox_for_import(canonical_url)
        rr = dict(_raw_row) if isinstance(_raw_row, dict) else {}
        pd = dict(product_data) if isinstance(product_data, dict) else {}
        title_like = rr.get("title")
        sku_like = rr.get("sku")
        pname = pd.get("name")
        basics = bool((title_like or "").strip() or (sku_like or "").strip() or (pname or "").strip())
        has_signal = basics or _hibox_row_shows_color_size_catalog(rr, pd)
        if has_signal:
            warn_txt = "; ".join(list(warns or [])[:6]).strip()
            return SourceStockCheckResult(status="in_stock", error=warn_txt or None)
        return SourceStockCheckResult(
            status="out_of_stock",
            error=(
                "Hibox không trả đủ dữ liệu PDP (thiếu tiêu đề/SKU và không có màu–size có nội dung)."
            ),
        )
    except ImportHiboxError as exc:
        return SourceStockCheckResult(status="error", error=str(exc)[:1000])
    except Exception as exc:
        logger.warning("hibox source stock evaluate failed: %s", exc)
        return SourceStockCheckResult(
            status="error",
            error=((str(exc) or "unexpected_error")[:920] + " — chưa kiểm tra được.")[:1000],
        )


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
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
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
    if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
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
            .filter(
                or_(
                    Product.link_default.ilike("%hibox.mn%"),
                    Product.link_default.ilike("%taobao1688.kz%"),
                    Product.link_default.ilike("%1688.com%"),
                    Product.link_default.ilike("%offer.1688%"),
                    Product.link_default.ilike("%detail.1688%"),
                    Product.link_default.ilike("%taobao.com%"),
                    Product.link_default.ilike("%tmall.com%"),
                )
            )
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
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
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


def check_product_source_stock(product_id: int) -> Optional[SourceStockCheckResult]:
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or not _link_eligible_for_hibox_stock_check(product.link_default or ""):
            return None
        previous_status = (product.source_stock_status or "").strip().lower()
        product.source_stock_status = "checking"
        product.source_stock_error = None
        product.source_stock_next_check_at = _utcnow()
        db.commit()

        result = _evaluate_stock_via_hibox(product.link_default or "")
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
