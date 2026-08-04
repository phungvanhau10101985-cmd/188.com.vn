"""
Hàng đợi xoá Bunny CDN bền vững (DB) + xử lý cron / thread nền.

Luồng:
  1. Khi xóa SP: ghi pending_bunny_deletes (storage_path unique)
  2. Thread nền (best-effort) + cron định kỳ: DELETE Bunny rồi xóa dòng
  3. Lỗi → tăng attempts, backoff next_attempt_at; quá max → status=failed
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.bunny_storage import (
    _bunny_image_hosts_for_delete,
    _url_to_storage_path,
    delete_file_from_zone,
)

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_paths(urls: Iterable[str]) -> List[Tuple[str, str]]:
    """Trả [(storage_path, source_url), ...] đã dedupe theo path."""
    hosts = _bunny_image_hosts_for_delete()
    if not hosts:
        return []
    out: List[Tuple[str, str]] = []
    seen: Set[str] = set()
    for raw in urls:
        u = str(raw or "").strip()
        if not u:
            continue
        path = _url_to_storage_path(u, hosts)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append((path, u))
    return out


def enqueue_pending_bunny_deletes(
    urls: Iterable[str],
    *,
    product_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> int:
    """
    Ghi URL vào bảng pending (durable). Trả số dòng mới hoặc re-queue từ failed.
    Có thể truyền ``db`` (cùng transaction) hoặc tự mở SessionLocal.
    """
    if not settings.BUNNY_DELETE_ON_PRODUCT_DELETE:
        return 0
    paths = _resolve_paths(urls)
    if not paths:
        return 0

    from app.models.pending_bunny_delete import PendingBunnyDelete

    own_session = db is None
    if own_session:
        from app.db.session import SessionLocal

        db = SessionLocal()

    assert db is not None
    pid = (str(product_id).strip() if product_id is not None else "") or None
    now = _now_utc()
    inserted = 0
    try:
        for storage_path, source_url in paths:
            row = (
                db.query(PendingBunnyDelete)
                .filter(PendingBunnyDelete.storage_path == storage_path)
                .first()
            )
            if row is None:
                db.add(
                    PendingBunnyDelete(
                        storage_path=storage_path,
                        source_url=source_url[:4000] if source_url else None,
                        product_id=pid,
                        status="pending",
                        attempts=0,
                        last_error=None,
                        next_attempt_at=now,
                    )
                )
                inserted += 1
            elif row.status == "failed":
                row.status = "pending"
                row.next_attempt_at = now
                row.last_error = None
                if pid and not row.product_id:
                    row.product_id = pid
                inserted += 1
            # pending đã có → bỏ qua (dedupe)
        db.commit()
        if inserted:
            logger.info("Bunny delete queue: enqueued/requeued %s path(s)", inserted)
        return inserted
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def process_pending_bunny_deletes(
    db: Session,
    *,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Xử lý một batch dòng pending đến hạn. Trả thống kê:
    ``{claimed, deleted, failed, skipped_config, remaining_pending}``
    """
    from app.models.pending_bunny_delete import PendingBunnyDelete

    batch = int(limit if limit is not None else getattr(settings, "BUNNY_DELETE_CRON_BATCH_SIZE", 80) or 80)
    batch = max(1, min(batch, 500))
    max_attempts = int(getattr(settings, "BUNNY_DELETE_MAX_ATTEMPTS", 8) or 8)
    max_attempts = max(1, min(max_attempts, 50))

    zone = (getattr(settings, "BUNNY_STORAGE_ZONE_NAME", "") or "").strip()
    key = (getattr(settings, "BUNNY_STORAGE_ACCESS_KEY", "") or "").strip()
    now = _now_utc()

    q = (
        db.query(PendingBunnyDelete)
        .filter(
            PendingBunnyDelete.status == "pending",
            PendingBunnyDelete.next_attempt_at <= now,
            PendingBunnyDelete.attempts < max_attempts,
        )
        .order_by(PendingBunnyDelete.id.asc())
    )
    if getattr(settings, "IS_POSTGRESQL", False):
        try:
            rows = q.with_for_update(skip_locked=True).limit(batch).all()
        except Exception:
            rows = q.limit(batch).all()
    else:
        rows = q.limit(batch).all()

    claimed = len(rows)
    deleted = 0
    failed = 0
    skipped_config = 0

    if not zone or not key:
        if claimed:
            logger.warning(
                "Bunny delete queue: thiếu BUNNY_STORAGE_* — giữ %s dòng pending",
                claimed,
            )
            skipped_config = claimed
        remaining = (
            db.query(PendingBunnyDelete)
            .filter(PendingBunnyDelete.status == "pending")
            .count()
        )
        return {
            "ok": True,
            "claimed": claimed,
            "deleted": 0,
            "failed": 0,
            "skipped_config": skipped_config,
            "remaining_pending": remaining,
        }

    for row in rows:
        row.attempts = int(row.attempts or 0) + 1
        try:
            ok = delete_file_from_zone(
                zone_name=zone,
                access_key=key,
                remote_path=row.storage_path,
            )
            if ok:
                db.delete(row)
                deleted += 1
            else:
                _mark_retry_or_failed(row, max_attempts, "Bunny DELETE không thành công (HTTP không 200/204/404)")
                failed += 1
        except Exception as exc:
            _mark_retry_or_failed(row, max_attempts, str(exc)[:1000])
            failed += 1

    db.commit()
    remaining = (
        db.query(PendingBunnyDelete)
        .filter(PendingBunnyDelete.status == "pending")
        .count()
    )
    if deleted or failed:
        logger.info(
            "Bunny delete queue: deleted=%s failed=%s claimed=%s remaining_pending=%s",
            deleted,
            failed,
            claimed,
            remaining,
        )
    return {
        "ok": True,
        "claimed": claimed,
        "deleted": deleted,
        "failed": failed,
        "skipped_config": skipped_config,
        "remaining_pending": remaining,
    }


def _mark_retry_or_failed(row: Any, max_attempts: int, error: str) -> None:
    row.last_error = error
    attempts = int(row.attempts or 0)
    if attempts >= max_attempts:
        row.status = "failed"
        row.next_attempt_at = _now_utc()
        return
    # Backoff: 1m, 2m, 4m… tối đa 1 giờ
    delay_sec = min(3600, 60 * (2 ** max(0, attempts - 1)))
    row.status = "pending"
    row.next_attempt_at = _now_utc() + timedelta(seconds=delay_sec)


def schedule_best_effort_bunny_queue_drain() -> None:
    """Thread nền: xử lý ngay một batch — cron vẫn quét lại phần còn / lỗi."""
    if not settings.BUNNY_DELETE_ON_PRODUCT_DELETE:
        return

    def _run() -> None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            process_pending_bunny_deletes(db)
        except Exception as exc:
            logger.warning("Bunny delete queue — drain nền lỗi (cron sẽ thử lại): %s", exc)
        finally:
            db.close()

    threading.Thread(target=_run, name="bulk-bunny-delete", daemon=True).start()


def enqueue_and_schedule_bunny_deletes(
    urls: Iterable[str],
    *,
    product_id: Optional[str] = None,
) -> int:
    """Ghi queue durable rồi kick thread nền (không chặn request)."""
    url_list = [str(u).strip() for u in urls if str(u or "").strip()]
    if not url_list:
        return 0
    n = enqueue_pending_bunny_deletes(url_list, product_id=product_id)
    schedule_best_effort_bunny_queue_drain()
    return n
