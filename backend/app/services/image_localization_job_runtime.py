"""Thread + resume cho job bản địa hóa ảnh (persist DB)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Set

from app.core.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_job_threads_lock = threading.Lock()
_job_threads_running: Set[str] = set()


def payload_from_stored(data: Any, payload_cls: type):
    if not isinstance(data, dict):
        return None
    try:
        return payload_cls(**data)
    except Exception:
        logger.exception("invalid stored image localization payload")
        return None


def mark_job_thread_running(job_id: str) -> bool:
    with _job_threads_lock:
        if job_id in _job_threads_running:
            return False
        _job_threads_running.add(job_id)
        return True


def unmark_job_thread_running(job_id: str) -> None:
    with _job_threads_lock:
        _job_threads_running.discard(job_id)


def start_job_thread(job_id: str, target: Callable[..., None], args: tuple, kwargs: dict) -> None:
    if not mark_job_thread_running(job_id):
        logger.warning("image localization job %s already running in this process", job_id)
        return

    def _wrap() -> None:
        try:
            target(*args, **kwargs)
        finally:
            unmark_job_thread_running(job_id)

    threading.Thread(target=_wrap, daemon=True, name=f"imgloc-{job_id[:8]}").start()


def resume_pending_jobs_after_startup(run_job: Callable[..., None], payload_cls: type) -> None:
    """Gọi từ FastAPI startup (thread daemon)."""
    if not getattr(settings, "IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP", True):
        return

    time.sleep(2.5)
    from app.crud import image_localization_job as job_crud

    db = SessionLocal()
    try:
        rows = job_crud.list_resumable_jobs(db, limit=30)
    finally:
        db.close()

    if not rows:
        return

    for row in rows:
        payload = payload_from_stored(row.payload, payload_cls)
        if payload is None:
            db_fail = SessionLocal()
            try:
                job_crud.patch_job(
                    db_fail,
                    row.job_id,
                    {
                        "status": "error",
                        "phase": "error",
                        "message": "Không khôi phục được cấu hình job sau restart.",
                    },
                )
            finally:
                db_fail.close()
            continue

        db_patch = SessionLocal()
        try:
            job_crud.patch_job(
                db_patch,
                row.job_id,
                {
                    "status": "queued",
                    "phase": "queued",
                    "message": (
                        f"Tiếp tục sau khởi động server "
                        f"(resume #{(row.resume_count or 0) + 1})…"
                    ),
                    "resume_count": (row.resume_count or 0) + 1,
                },
            )
        finally:
            db_patch.close()

        logger.info("IMAGE_LOCALIZATION_JOB_RESUME job_id=%s", row.job_id)
        start_job_thread(row.job_id, run_job, (row.job_id, payload), {"resume": True})


def start_resume_daemon(run_job: Callable[..., None], payload_cls: type) -> None:
    t = threading.Thread(
        target=resume_pending_jobs_after_startup,
        args=(run_job, payload_cls),
        daemon=True,
        name="image-localization-job-resume",
    )
    t.start()
