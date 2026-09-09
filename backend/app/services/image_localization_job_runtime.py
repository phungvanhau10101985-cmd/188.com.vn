"""Process + resume cho job bản địa hóa ảnh (persist DB). Hủy ngay = terminate subprocess."""

from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]

from app.core.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_job_threads_lock = threading.Lock()
_job_threads_running: Set[str] = set()

_proc_lock = threading.Lock()
_job_processes: Dict[str, multiprocessing.Process] = {}


def worker_process_title(job_id: str) -> str:
    """Tên /proc/comm — tối đa 15 ký tự (prctl)."""
    return f"imgloc-{(job_id or '')[:8]}"


def cmdline_looks_like_imgloc_worker(comm: str, cmdline: str) -> bool:
    comm_s = (comm or "").strip()
    cmd = cmdline or ""
    if comm_s.startswith("imgloc-"):
        return True
    if "resource_tracker" in cmd:
        return False
    return "multiprocessing.spawn" in cmd or "_multiprocess_job_entry" in cmd


def should_abort_auto_resume(*, resume_count: int, max_resume: int) -> bool:
    """resume_count = số lần resume liên tiếp không xong thêm SP. 0 = không giới hạn."""
    if max_resume <= 0:
        return False
    return int(resume_count or 0) >= int(max_resume)


def job_updated_at_is_stalled(
    updated_at: Optional[datetime],
    *,
    stall_seconds: int,
    now: Optional[datetime] = None,
) -> bool:
    if stall_seconds <= 0 or updated_at is None:
        return False
    ts = updated_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    return (clock - ts).total_seconds() >= stall_seconds


def _set_worker_process_title(job_id: str) -> None:
    name = worker_process_title(job_id)
    try:
        with open("/proc/self/comm", "w", encoding="utf-8") as fh:
            fh.write(name[:15])
    except Exception:
        pass
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(15, name.encode("utf-8")[:15], 0, 0, 0)
    except Exception:
        pass
    try:
        sys.argv[0] = name
    except Exception:
        pass


def _iter_imgloc_os_workers() -> List[Tuple[int, int, str]]:
    """(pid, ppid, cmdline) — Linux /proc. Rỗng trên Windows."""
    out: List[Tuple[int, int, str]] = []
    proc_root = "/proc"
    try:
        names = os.listdir(proc_root)
    except Exception:
        return out
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        base = f"{proc_root}/{pid}"
        try:
            with open(f"{base}/comm", "r", encoding="utf-8", errors="replace") as fh:
                comm = fh.read().strip()
            with open(f"{base}/cmdline", "rb") as fh:
                cmd = fh.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
            ppid = 0
            with open(f"{base}/status", "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        break
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, OSError):
            continue
        if cmdline_looks_like_imgloc_worker(comm, cmd):
            out.append((pid, ppid, cmd or comm))
    return out


def tracked_worker_pids() -> Set[int]:
    with _proc_lock:
        pids: Set[int] = set()
        for proc in _job_processes.values():
            pid = getattr(proc, "pid", None)
            if pid and proc.is_alive():
                pids.add(int(pid))
        return pids


def reap_untracked_imgloc_workers() -> int:
    """Giết worker spawn mồ côi (ppid=1 sau SIGKILL/deploy) — không đụng worker con của API hiện tại."""
    tracked = tracked_worker_pids()
    killed = 0
    for pid, ppid, cmd in _iter_imgloc_os_workers():
        if pid in tracked or pid == os.getpid():
            continue
        if ppid not in (0, 1):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            logger.warning("reap orphan imgloc worker pid=%s cmd=%s", pid, (cmd or "")[:120])
        except ProcessLookupError:
            continue
        except Exception:
            logger.exception("reap imgloc worker pid=%s failed", pid)
    if killed:
        time.sleep(0.4)
        for pid, ppid, _cmd in _iter_imgloc_os_workers():
            if pid in tracked or pid == os.getpid() or ppid not in (0, 1):
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
    return killed


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
    if resource is None:
        return
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
        _set_worker_process_title(job_id)
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
    title = worker_process_title(jid)
    for pkill_args in (
        ["pkill", "-x", title],
        ["pkill", "-f", title],
    ):
        try:
            subprocess.run(
                pkill_args,
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

    from app.crud import image_localization_job as job_crud

    db = SessionLocal()
    try:
        rows = job_crud.list_resumable_jobs(db, limit=30)
    finally:
        db.close()

    if not rows:
        return

    reap_untracked_imgloc_workers()

    blocked, detail = memory_pressure_blocks_imgloc()
    if blocked:
        logger.warning(
            "IMAGE_LOCALIZATION_JOB_RESUME deferred — memory pressure (%s)",
            detail,
        )
        for row in rows:
            if _job_worker_alive(row.job_id):
                continue
            db_wait = SessionLocal()
            try:
                job_crud.patch_job(
                    db_wait,
                    row.job_id,
                    {
                        "status": "queued",
                        "phase": "queued",
                        "message": f"Tạm chờ RAM rồi tiếp tục ({detail}).",
                    },
                )
            finally:
                db_wait.close()
        return

    max_resume = int(getattr(settings, "IMAGE_LOCALIZATION_MAX_AUTO_RESUME_COUNT", 6) or 6)
    stall_seconds = int(getattr(settings, "IMAGE_LOCALIZATION_JOB_STALL_SECONDS", 1200) or 0)

    for row in rows:
        if _job_worker_alive(row.job_id):
            db_stall = SessionLocal()
            try:
                fresh_alive = job_crud.get_job(db_stall, row.job_id)
            finally:
                db_stall.close()
            if fresh_alive and job_updated_at_is_stalled(
                fresh_alive.updated_at, stall_seconds=stall_seconds
            ):
                logger.warning(
                    "IMAGE_LOCALIZATION_JOB stall job_id=%s updated_at=%s — kill rồi resume",
                    row.job_id,
                    fresh_alive.updated_at,
                )
                terminate_job_worker(row.job_id)
            else:
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
            if should_abort_auto_resume(resume_count=resume_n, max_resume=max_resume):
                job_crud.patch_job(
                    db_check,
                    row.job_id,
                    {
                        "status": "error",
                        "phase": "error",
                        "message": (
                            f"Dừng auto-resume sau {resume_n} lần liên tiếp không tiến thêm SP "
                            "(có thể do OOM). Bấm chạy lại job thủ công khi server ổn định."
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
