"""Process + resume cho job bản địa hóa ảnh (persist DB). Hủy ngay = terminate subprocess."""

from __future__ import annotations

import logging
import multiprocessing
import resource
import subprocess
import threading
import time
from typing import Any, Dict, Optional, Set, Tuple

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


def _mem_available_mb() -> Optional[int]:
    """Đọc MemAvailable từ /proc (Linux). None nếu không đọc được."""
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    # giá trị là kB
                    return int(parts[1]) // 1024
    except Exception:
        return None
    return None


def _apply_worker_address_space_limit() -> None:
    """Giới hạn RLIMIT_AS của worker — OOM trong job ảnh không nuốt hết RAM VPS."""
    max_mb = int(getattr(settings, "IMAGE_LOCALIZATION_WORKER_MAX_AS_MB", 0) or 0)
    if max_mb <= 0:
        return
    try:
        limit = max_mb * 1024 * 1024
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = hard if hard != resource.RLIM_INFINITY and hard < limit else limit
        new_soft = min(limit, new_hard) if new_hard != resource.RLIM_INFINITY else limit
        resource.setrlimit(resource.RLIMIT_AS, (new_soft, new_hard))
        logger.info(
            "IMAGE_LOCALIZATION_WORKER RLIMIT_AS soft=%sMB hard=%sMB",
            new_soft // (1024 * 1024),
            "inf" if new_hard == resource.RLIM_INFINITY else new_hard // (1024 * 1024),
        )
    except Exception:
        logger.exception("Không set được RLIMIT_AS cho image localization worker")


def memory_pressure_blocks_imgloc() -> Tuple[bool, str]:
    """
    True = không nên start/resume job ảnh (RAM trống thấp).
    """
    min_mb = int(getattr(settings, "IMAGE_LOCALIZATION_RESUME_MIN_AVAILABLE_MB", 2800) or 0)
    if min_mb <= 0:
        return False, ""
    avail = _mem_available_mb()
    if avail is None:
        return False, ""
    if avail < min_mb:
        return True, f"MemAvailable={avail}MB < min={min_mb}MB"
    return False, f"MemAvailable={avail}MB"


def _multiprocess_job_entry(job_id: str, payload_dict: dict, resume: bool) -> None:
    try:
        _apply_worker_address_space_limit()
        from app.api.endpoints.image_localization import StartImageLocalizationPayload, _run_job

        payload = StartImageLocalizationPayload(**payload_dict)
        _run_job(job_id, payload, resume=resume)
    except MemoryError:
        logger.exception(
            "image localization subprocess OOM (MemoryError) job_id=%s — worker bị giới hạn RAM",
            job_id,
        )
        try:
            from app.crud import image_localization_job as job_crud

            db = SessionLocal()
            try:
                job_crud.patch_job(
                    db,
                    job_id,
                    {
                        "status": "error",
                        "phase": "error",
                        "message": (
                            "Job dừng vì hết RAM worker (RLIMIT). "
                            "Chạy lại khi server rảnh hoặc giảm MERGE_MAX_PIXELS."
                        ),
                    },
                )
            finally:
                db.close()
        except Exception:
            logger.exception("failed to mark imgloc job error after MemoryError")
    except Exception:
        logger.exception("image localization subprocess job %s failed", job_id)
    finally:
        _unregister_process(job_id)
        unmark_job_thread_running(job_id)


def start_job_process(job_id: str, payload_dict: dict, *, resume: bool = False) -> None:
    """Chạy job trong subprocess riêng — hủy ngay có thể terminate process."""
    blocked, detail = memory_pressure_blocks_imgloc()
    if blocked:
        logger.warning(
            "IMAGE_LOCALIZATION_JOB_PROCESS skip job_id=%s — memory pressure (%s)",
            job_id,
            detail,
        )
        return
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
    logger.info(
        "IMAGE_LOCALIZATION_JOB_PROCESS start job_id=%s pid=%s (%s)",
        job_id,
        proc.pid,
        detail or "mem-ok",
    )


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
    killed = False
    with _proc_lock:
        proc = _job_processes.get(jid)
    if proc is not None:
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
            killed = True
        except Exception:
            logger.exception("terminate_job_worker failed job_id=%s", jid)
        finally:
            _unregister_process(jid)
            unmark_job_thread_running(jid)
    try:
        subprocess.run(
            ["pkill", "-f", f"imgloc-{jid[:8]}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        killed = True
    except Exception:
        pass
    if not killed:
        unmark_job_thread_running(jid)
    return killed


def get_job_worker_pid(job_id: str) -> Optional[int]:
    with _proc_lock:
        proc = _job_processes.get((job_id or "").strip())
    if proc is None:
        return None
    return getattr(proc, "pid", None)


def _job_worker_alive(job_id: str) -> bool:
    with _proc_lock:
        proc = _job_processes.get((job_id or "").strip())
    return proc is not None and proc.is_alive()


def _clear_stale_job_thread_mark(job_id: str) -> None:
    """Worker subprocess chết giữa chừng (deploy/restart) — bỏ cờ in-memory để resume lại."""
    if _job_worker_alive(job_id):
        return
    with _job_threads_lock:
        _job_threads_running.discard(job_id)


def resume_pending_jobs(run_job, payload_cls: type) -> None:
    """Resume job queued/running trong DB nếu chưa có worker subprocess sống."""
    if not getattr(settings, "IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP", True):
        return

    blocked, detail = memory_pressure_blocks_imgloc()
    if blocked:
        logger.warning(
            "IMAGE_LOCALIZATION_JOB_RESUME deferred — memory pressure (%s)",
            detail,
        )
        return

    from app.crud import image_localization_job as job_crud

    db = SessionLocal()
    try:
        rows = job_crud.list_resumable_jobs(db, limit=30)
    finally:
        db.close()

    if not rows:
        return

    max_resume = int(getattr(settings, "IMAGE_LOCALIZATION_MAX_AUTO_RESUME_COUNT", 6) or 6)

    for row in rows:
        if _job_worker_alive(row.job_id):
            continue
        _clear_stale_job_thread_mark(row.job_id)

        db_check = SessionLocal()
        try:
            fresh = job_crud.get_job(db_check, row.job_id)
            if not fresh:
                continue
            st = (fresh.status or "").strip().lower()
            if st in ("cancelled", "done", "error") or bool(fresh.cancel_requested):
                logger.info("IMAGE_LOCALIZATION_JOB_RESUME skip job_id=%s status=%s", row.job_id, st)
                continue
            resume_n = int(fresh.resume_count or 0)
            if max_resume > 0 and resume_n >= max_resume:
                job_crud.patch_job(
                    db_check,
                    row.job_id,
                    {
                        "status": "error",
                        "phase": "error",
                        "message": (
                            f"Dừng auto-resume sau {resume_n} lần (có thể do OOM). "
                            "Bấm chạy lại job thủ công khi server ổn định."
                        ),
                    },
                )
                logger.error(
                    "IMAGE_LOCALIZATION_JOB_RESUME aborted job_id=%s resume_count=%s",
                    row.job_id,
                    resume_n,
                )
                continue
        finally:
            db_check.close()

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


def resume_pending_jobs_after_startup(run_job, payload_cls: type) -> None:
    """Gọi từ FastAPI startup (thread daemon)."""
    time.sleep(2.5)
    resume_pending_jobs(run_job, payload_cls)


def _resume_daemon_loop(run_job, payload_cls: type) -> None:
    resume_pending_jobs_after_startup(run_job, payload_cls)
    interval = max(
        60,
        int(getattr(settings, "IMAGE_LOCALIZATION_JOB_ORPHAN_CHECK_SECONDS", 180)),
    )
    while True:
        time.sleep(interval)
        try:
            resume_pending_jobs(run_job, payload_cls)
        except Exception:
            logger.exception("image localization orphan resume loop failed")


def start_resume_daemon(run_job, payload_cls: type) -> None:
    t = threading.Thread(
        target=_resume_daemon_loop,
        args=(run_job, payload_cls),
        daemon=True,
        name="image-localization-job-resume",
    )
    t.start()
