"""Tra EMS nền sau import / cron hàng ngày — tránh block request HTTP."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.order_shipment import EmsShippingRecord
from app.services import ems_shipment_import as ems_import_svc

logger = logging.getLogger(__name__)

_SAFE_JOB_ID = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)
_TERMINAL_PHASES = frozenset({"delivered", "cod_collected", "cod_settled"})

_JOB_QUEUE: queue.Queue[tuple[str, list[int], Optional[int], str]] = queue.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def _jobs_root() -> Path:
    backend = Path(__file__).resolve().parents[2]
    d = backend / "temp_uploads" / "ems_tracking_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _persist_job(job_id: str, state: dict[str, Any]) -> None:
    if not _SAFE_JOB_ID.match(job_id or ""):
        return
    path = _jobs_root() / f"{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def _load_job(job_id: str) -> Optional[dict[str, Any]]:
    if not _SAFE_JOB_ID.match(job_id or ""):
        return None
    path = _jobs_root() / f"{job_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _job_update(job_id: str, **kwargs: Any) -> None:
    with _WORKER_LOCK:
        state = _JOBS.get(job_id) or _load_job(job_id) or {"job_id": job_id}
        state.update(kwargs)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _JOBS[job_id] = state
        _persist_job(job_id, state)


def get_tracking_refresh_job(job_id: str) -> Optional[dict[str, Any]]:
    with _WORKER_LOCK:
        job = _JOBS.get(job_id) or _load_job(job_id)
        if job:
            _JOBS[job_id] = job
        return job


def _refresh_delay_seconds() -> float:
    return max(0.2, float(getattr(settings, "EMS_TRACKING_REFRESH_DELAY_SECONDS", 0.6) or 0.6))


def refresh_ems_record_by_id(db: Session, record_id: int, *, admin_id: Optional[int] = None) -> dict[str, Any]:
    record = db.query(EmsShippingRecord).filter(EmsShippingRecord.id == record_id).first()
    if not record:
        return {"ok": False, "record_id": record_id, "error": "record_not_found"}

    row = {
        "row_number": record.excel_row_number or 0,
        "reference_code": record.reference_code,
        "recipient_label": record.recipient_label or "",
        "order_code": record.order_code,
        "cod_amount": int(record.cod_amount) if record.cod_amount is not None else None,
    }
    result = ems_import_svc.process_ems_import_row(
        db,
        row,
        admin_id=admin_id,
        skip_ems_tracking=False,
    )
    ems_import_svc._upsert_record(db, result, admin_id=admin_id)
    db.commit()
    return {
        "ok": True,
        "record_id": record_id,
        "reference_code": record.reference_code,
        "sync_status": result.get("sync_status"),
        "ems_tracking_code": result.get("ems_tracking_code"),
    }


def collect_record_ids_for_daily_refresh(db: Session, *, limit: Optional[int] = None) -> list[int]:
    batch_limit = limit or int(getattr(settings, "EMS_TRACKING_DAILY_BATCH_LIMIT", 400) or 400)
    batch_limit = max(1, min(batch_limit, 2000))

    rows = (
        db.query(EmsShippingRecord.id)
        .filter(
            or_(
                EmsShippingRecord.ems_tracking_code.is_(None),
                EmsShippingRecord.ems_phase.is_(None),
                EmsShippingRecord.ems_phase.notin_(tuple(_TERMINAL_PHASES)),
            ),
        )
        .order_by(
            EmsShippingRecord.ems_tracking_code.asc().nullsfirst(),
            EmsShippingRecord.updated_at.asc().nullsfirst(),
            EmsShippingRecord.id.asc(),
        )
        .limit(batch_limit)
        .all()
    )
    return [int(r[0]) for r in rows]


def enqueue_tracking_refresh(
    record_ids: list[int],
    *,
    admin_id: Optional[int] = None,
    source: str = "manual",
) -> Optional[str]:
    if not getattr(settings, "EMS_TRACKING_REFRESH_ENABLED", True):
        return None
    ids = [int(x) for x in record_ids if int(x) > 0]
    if not ids:
        return None

    job_id = str(uuid.uuid4())
    initial = {
        "job_id": job_id,
        "status": "queued",
        "source": source,
        "total": len(ids),
        "processed": 0,
        "ok": 0,
        "errors": 0,
        "message": "Đang chờ tra EMS…",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _WORKER_LOCK:
        _JOBS[job_id] = initial
        _persist_job(job_id, initial)

    _JOB_QUEUE.put((job_id, ids, admin_id, source))
    _ensure_worker_started()
    return job_id


def _execute_job(job_id: str, record_ids: list[int], admin_id: Optional[int], source: str) -> None:
    total = len(record_ids)
    _job_update(
        job_id,
        status="running",
        total=total,
        processed=0,
        ok=0,
        errors=0,
        message=f"Đang tra EMS ({source})…",
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    ok = errors = 0
    delay = _refresh_delay_seconds()

    for idx, record_id in enumerate(record_ids, start=1):
        db = SessionLocal()
        try:
            out = refresh_ems_record_by_id(db, record_id, admin_id=admin_id)
            if out.get("ok"):
                ok += 1
            else:
                errors += 1
        except Exception as exc:
            errors += 1
            logger.warning("EMS refresh failed record_id=%s: %s", record_id, exc)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()

        _job_update(
            job_id,
            processed=idx,
            ok=ok,
            errors=errors,
            message=f"Đang tra EMS: {idx}/{total} (ok {ok}, lỗi {errors})",
        )
        if idx < total:
            time.sleep(delay)

    _job_update(
        job_id,
        status="completed",
        processed=total,
        ok=ok,
        errors=errors,
        message=f"Hoàn tất tra EMS: {ok}/{total} thành công, {errors} lỗi.",
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


def _worker_loop() -> None:
    while True:
        job_id, record_ids, admin_id, source = _JOB_QUEUE.get()
        try:
            _execute_job(job_id, record_ids, admin_id, source)
        except Exception as exc:
            logger.exception("EMS tracking refresh job crashed job_id=%s: %s", job_id, exc)
            _job_update(
                job_id,
                status="failed",
                message=f"Lỗi job tra EMS: {exc}",
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
        finally:
            _JOB_QUEUE.task_done()


def _ensure_worker_started() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker_loop, name="ems-tracking-refresh", daemon=True)
        thread.start()
        _WORKER_STARTED = True


def start_ems_tracking_refresh_worker_if_enabled() -> None:
    if not getattr(settings, "EMS_TRACKING_REFRESH_ENABLED", True):
        return
    _ensure_worker_started()


def run_daily_ems_tracking_refresh(db: Session) -> dict[str, Any]:
    record_ids = collect_record_ids_for_daily_refresh(db)
    if not record_ids:
        return {"ok": True, "queued": 0, "job_id": None, "message": "Không có bản ghi cần tra EMS."}
    job_id = enqueue_tracking_refresh(record_ids, source="daily_cron")
    return {
        "ok": True,
        "queued": len(record_ids),
        "job_id": job_id,
        "message": f"Đã xếp hàng tra EMS cho {len(record_ids)} bản ghi.",
    }
