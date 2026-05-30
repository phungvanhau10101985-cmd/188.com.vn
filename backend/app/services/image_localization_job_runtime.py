"""Process + resume cho job bản địa hóa ảnh (persist DB). Hủy ngay = terminate subprocess."""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from typing import Any, Dict, Optional, Set

from app.core.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_job_threads_lock = threading.Lock()
_job_threads_running: Set[str] = set()

_proc_lock = threading.Lock()
_job_processes: Dict[str, multiprocessing.Process] = {}


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


def _unregister_process(job_id: str) -> None:
    with _proc_lock:
        _job_processes.pop(job_id, None)


def _multiprocess_job_entry(job_id: str, payload_dict: dict, resume: bool) -> None:
    try:
        from app.api.endpoints.image_localization import StartImageLocalizationPayload, _run_job

        payload = StartImageLocalizationPayload(**payload_dict)
        _run_job(job_id, payload, resume=resume)
    except Exception:
        logger.exception("image localization subprocess job %s failed", job_id)
    finally:
        _unregister_process(job_id)
        unmark_job_thread_running(job_id)


def start_job_process(job_id: str, payload_dict: dict, *, resume: bool = False) -> None:
    """Chạy job trong subprocess riêng — hủy ngay có thể terminate process."""
    if not mark_job_thread_running(job_id):
        logger.warning("image localization job %s already running in this process", job_id)
        return
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(
        target=_multiprocess_job_entry,
        args=(job_id, payload_dict, resume),
        daemon=True,
        name=f"imgloc-{job_id[:8]}",
    )
    proc.start()
    with _proc_lock:
        _job_processes[job_id] = proc
    logger.info("IMAGE_LOCALIZATION_JOB_PROCESS start job_id=%s pid=%s", job_id, proc.pid)


def start_job_thread(job_id: str, target, args: tuple, kwargs: dict) -> None:
    """Deprecated — giữ tương thích; ưu tiên start_job_process."""
    if not mark_job_thread_running(job_id):
        logger.warning("image localization job %s already running in this process", job_id)
        return

    def _wrap() -> None:
        try:
            target(*args, **kwargs)
        finally:
            unmark_job_thread_running(job_id)

    threading.Thread(target=_wrap, daemon=True, name=f"imgloc-{job_id[:8]}").start()


def terminate_job_worker(job_id: str) -> bool:
    """Hủy ngay: kill subprocess đang chạy job (OCR/Gemini/Playwright)."""
    jid = (job_id or "").strip()
    if not jid:
        return False
    with _proc_lock:
        proc = _job_processes.get(jid)
    if proc is None:
        return False
    pid = getattr(proc, "pid", None)
    try:
        if proc.is_alive():
            logger.warning("terminate image localization job job_id=%s pid=%s", jid, pid)
            proc.terminate()
            proc.join(timeout=8)
        if proc.is_alive():
            logger.warning("kill image localization job job_id=%s pid=%s", jid, pid)
            proc.kill()
            proc.join(timeout=5)
    except Exception:
        logger.exception("terminate_job_worker failed job_id=%s", jid)
    finally:
        _unregister_process(jid)
        unmark_job_thread_running(jid)
    return True


def get_job_worker_pid(job_id: str) -> Optional[int]:
    with _proc_lock:
        proc = _job_processes.get((job_id or "").strip())
    if proc is None:
        return None
    return getattr(proc, "pid", None)


def resume_pending_jobs_after_startup(run_job, payload_cls: type) -> None:
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
        start_job_process(row.job_id, payload.model_dump(), resume=True)


def start_resume_daemon(run_job, payload_cls: type) -> None:
    t = threading.Thread(
        target=resume_pending_jobs_after_startup,
        args=(run_job, payload_cls),
        daemon=True,
        name="image-localization-job-resume",
    )
    t.start()
