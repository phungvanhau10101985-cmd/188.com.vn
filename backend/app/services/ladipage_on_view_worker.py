# backend/app/services/ladipage_on_view_worker.py
"""
Tạo ladipage 1 SP theo nhu cầu: khi khách xem PDP hoặc quét SP có traffic gần đây.

Ưu tiên SP có lượt xem thay vì bootstrap cả catalog (~36k).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional, Set

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.product import Product
from app.services.admin_source_stock_batch import recent_customer_view_exists
from app.services.ladipage_bootstrap import bootstrap_single_product_ladipage, product_ids_with_single_ladipage
from app.services.ladipage_cleanup import find_single_product_ladipages_for_product

logger = logging.getLogger(__name__)

_queue_lock = threading.Lock()
_worker_lock = threading.Lock()
_queue: Deque[int] = deque()
_queued_ids: Set[int] = set()
_worker_started = False
_worker_thread_ref: Optional[threading.Thread] = None
_last_scan_at: Optional[datetime] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ladipage_on_view_enabled() -> bool:
    return bool(getattr(settings, "LADIPAGE_ON_VIEW_ENABLED", True))


def ladipage_on_view_traffic_window_days() -> int:
    return max(
        1,
        int(
            getattr(
                settings,
                "LADIPAGE_ON_VIEW_TRAFFIC_WINDOW_DAYS",
                getattr(settings, "ADMIN_SOURCE_BATCH_TRAFFIC_VIEW_WINDOW_DAYS", 30),
            )
        ),
    )


def _traffic_view_window_since() -> datetime:
    return _utcnow() - timedelta(days=ladipage_on_view_traffic_window_days())


def get_ladipage_on_view_queue_depth() -> int:
    with _queue_lock:
        return len(_queue)


def _should_skip_product(db: Session, product_id: int) -> bool:
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.is_active:
        return True
    if find_single_product_ladipages_for_product(db, product_id):
        return True
    return False


def enqueue_ladipage_on_view_if_needed(product_id: int, *, reason: str = "product_view") -> bool:
    """Đưa SP vào hàng chờ sinh ladipage — gọi sau khi ghi product view."""
    if not ladipage_on_view_enabled():
        return False
    try:
        pid = int(product_id)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False

    with _queue_lock:
        if pid in _queued_ids:
            return False
        _queued_ids.add(pid)
        _queue.append(pid)

    logger.info("ladipage on-view queued: product_id=%s reason=%s", pid, reason)
    return True


def _pop_queued_product_id() -> Optional[int]:
    with _queue_lock:
        if not _queue:
            return None
        product_id = _queue.popleft()
        _queued_ids.discard(product_id)
        return product_id


def _scan_and_enqueue_backlog(limit: int) -> int:
    """SP active có khách xem gần đây nhưng chưa có ladipage 1 SP."""
    global _last_scan_at
    now = _utcnow()
    scan_interval = max(
        60,
        int(getattr(settings, "LADIPAGE_ON_VIEW_SCAN_INTERVAL_SECONDS", 900) or 900),
    )
    if _last_scan_at and (now - _last_scan_at).total_seconds() < scan_interval:
        return 0
    _last_scan_at = now

    view_since = _traffic_view_window_since()
    db = SessionLocal()
    try:
        covered = product_ids_with_single_ladipage(db)
        rows = (
            db.query(Product.id)
            .filter(Product.is_active.is_(True))
            .filter(recent_customer_view_exists(Product, view_since))
            .order_by(Product.id.asc())
            .limit(max(1, limit) * 4)
            .all()
        )
        enqueued = 0
        for (pid,) in rows:
            if pid in covered:
                continue
            if enqueue_ladipage_on_view_if_needed(int(pid), reason="traffic_scan"):
                enqueued += 1
            if enqueued >= limit:
                break
        if enqueued:
            logger.info("ladipage on-view scan enqueued %s product(s)", enqueued)
        return enqueued
    finally:
        db.close()


def _process_one_product(product_id: int) -> None:
    db = SessionLocal()
    try:
        if _should_skip_product(db, product_id):
            logger.info("ladipage on-view skip product_id=%s (inactive or already has ladipage)", product_id)
            return
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return
        publish = bool(getattr(settings, "LADIPAGE_ON_VIEW_PUBLISH", True))
        lp = bootstrap_single_product_ladipage(db, product, publish=publish, skip_if_exists=True)
        if lp:
            logger.info(
                "ladipage on-view done: product_id=%s ladipage_id=%s slug=%s status=%s",
                product_id,
                lp.id,
                lp.slug,
                lp.status,
            )
        else:
            logger.info("ladipage on-view noop product_id=%s (race / already exists)", product_id)
    except Exception as exc:
        db.rollback()
        logger.warning("ladipage on-view failed product_id=%s: %s", product_id, exc)
    finally:
        db.close()


def _worker_loop() -> None:
    idle_sleep = max(
        5,
        int(getattr(settings, "LADIPAGE_ON_VIEW_WORKER_INTERVAL_SECONDS", 15) or 15),
    )
    job_sleep = max(
        0.0,
        float(getattr(settings, "LADIPAGE_ON_VIEW_SLEEP_BETWEEN_JOBS", 0.35) or 0.35),
    )
    scan_batch = max(1, int(getattr(settings, "LADIPAGE_ON_VIEW_SCAN_BATCH_SIZE", 15) or 15))

    logger.info(
        "ladipage on-view worker started: idle=%ss publish=%s window=%sd",
        idle_sleep,
        getattr(settings, "LADIPAGE_ON_VIEW_PUBLISH", True),
        ladipage_on_view_traffic_window_days(),
    )

    while True:
        if not ladipage_on_view_enabled():
            time.sleep(idle_sleep)
            continue

        product_id = _pop_queued_product_id()
        if product_id is None:
            _scan_and_enqueue_backlog(scan_batch)
            product_id = _pop_queued_product_id()
        if product_id is None:
            time.sleep(idle_sleep)
            continue

        _process_one_product(product_id)
        if job_sleep > 0:
            time.sleep(job_sleep)


def start_ladipage_on_view_worker_if_enabled() -> None:
    if not ladipage_on_view_enabled():
        return
    global _worker_started, _worker_thread_ref
    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True
        thread = threading.Thread(target=_worker_loop, name="ladipage-on-view", daemon=True)
        _worker_thread_ref = thread
        thread.start()
