"""Chạy deploy/backup-vps.sh, lịch backup & quét file trên VPS."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.vps_backup import VpsBackupRun, VpsBackupSettings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKUP_SCRIPT = PROJECT_ROOT / "deploy" / "backup-vps.sh"
DEFAULT_BACKUP_ROOT = "/var/backups/188.com.vn"
ARCHIVE_RE = re.compile(r"^backup-188-\d{8}-\d{6}\.tar\.gz$")
DEFAULT_KEEP_COUNT = 2

_scheduler_lock = threading.Lock()
_scheduler_started = False
_backup_job_lock = threading.Lock()
_backup_job_running = False


def backup_root_dir() -> Path:
    raw = (os.getenv("BACKUP_ROOT") or DEFAULT_BACKUP_ROOT).strip()
    return Path(raw)


def is_backup_environment_available() -> bool:
    if os.name == "nt":
        return False
    return BACKUP_SCRIPT.is_file()


def pretty_bytes(num: Optional[int]) -> str:
    if num is None or num < 0:
        return "—"
    n = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def normalize_days_of_week(days: Optional[List[int]]) -> List[int]:
    if not days:
        return [0, 1, 2, 3, 4, 5, 6]
    out = sorted({int(d) for d in days if isinstance(d, (int, float)) and 0 <= int(d) <= 6})
    return out or [0, 1, 2, 3, 4, 5, 6]


def effective_keep_count(row: Optional[VpsBackupSettings]) -> int:
    if not row:
        return DEFAULT_KEEP_COUNT
    kc = getattr(row, "keep_count", None)
    if kc is not None and int(kc) > 0:
        return int(kc)
    return DEFAULT_KEEP_COUNT


def get_or_create_settings(db: Session) -> VpsBackupSettings:
    row = db.query(VpsBackupSettings).filter(VpsBackupSettings.id == 1).first()
    if row:
        row.days_of_week = normalize_days_of_week(row.days_of_week)
        if int(getattr(row, "keep_count", None) or 0) != DEFAULT_KEEP_COUNT:
            row.keep_count = DEFAULT_KEEP_COUNT
            row.retention_days = DEFAULT_KEEP_COUNT
            db.commit()
        return row
    row = VpsBackupSettings(
        id=1,
        enabled=False,
        hour=3,
        minute=0,
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        keep_count=DEFAULT_KEEP_COUNT,
        retention_days=DEFAULT_KEEP_COUNT,
        include_cache=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def settings_to_payload(row: VpsBackupSettings) -> dict:
    kc = effective_keep_count(row)
    payload = {
        "enabled": bool(row.enabled),
        "hour": int(row.hour or 0),
        "minute": int(row.minute or 0),
        "days_of_week": normalize_days_of_week(row.days_of_week),
        "keep_count": kc,
        "include_cache": bool(row.include_cache),
        "notify_on_complete": True,
        "last_triggered_at": row.last_triggered_at,
        "updated_at": row.updated_at,
        "backup_available": is_backup_environment_available(),
        "backup_root": str(backup_root_dir()),
        "script_path": str(BACKUP_SCRIPT),
    }
    from app.services.vps_backup_drive import drive_settings_payload

    payload.update(drive_settings_payload())
    return payload


def update_settings(db: Session, payload: dict) -> VpsBackupSettings:
    row = get_or_create_settings(db)
    row.enabled = bool(payload.get("enabled", False))
    row.hour = int(payload.get("hour", 3))
    row.minute = int(payload.get("minute", 0))
    row.days_of_week = normalize_days_of_week(payload.get("days_of_week"))
    row.keep_count = DEFAULT_KEEP_COUNT
    row.retention_days = DEFAULT_KEEP_COUNT
    row.include_cache = bool(payload.get("include_cache", False))
    db.commit()
    db.refresh(row)
    return row


def resolve_archive_path(filename: str) -> Path:
    name = Path(filename).name
    if not ARCHIVE_RE.match(name):
        raise ValueError("Tên file backup không hợp lệ.")
    path = (backup_root_dir() / name).resolve()
    root = backup_root_dir().resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("Đường dẫn file không hợp lệ.")
    return path


def _find_newest_archive(since_ts: float) -> Optional[Path]:
    root = backup_root_dir()
    if not root.is_dir():
        return None
    candidates: List[Tuple[float, Path]] = []
    for p in root.glob("backup-188-*.tar.gz"):
        if not p.is_file() or not ARCHIVE_RE.match(p.name):
            continue
        mtime = p.stat().st_mtime
        if mtime >= since_ts - 5:
            candidates.append((mtime, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _finish_run_notify(db: Session, run: VpsBackupRun) -> None:
    try:
        from app.services.vps_backup_notify import notify_backup_finished

        notify_backup_finished(
            run_id=run.id,
            status=run.status,
            trigger=run.trigger,
            archive_filename=run.archive_filename,
            archive_size_pretty=pretty_bytes(run.archive_size_bytes),
            error_message=run.error_message,
            drive_upload_status=run.drive_upload_status,
            drive_web_link=run.drive_web_link,
            drive_upload_error=run.drive_upload_error,
        )
    except Exception:
        logger.exception("VPS backup notify failed for run_id=%s (backup result unchanged)", run.id)


def _execute_backup_run(run_id: int) -> None:
    global _backup_job_running
    db = SessionLocal()
    started_ts = time.time()
    run: Optional[VpsBackupRun] = None
    try:
        run = db.query(VpsBackupRun).filter(VpsBackupRun.id == run_id).first()
        if not run:
            return
        if not is_backup_environment_available():
            run.status = "failed"
            run.error_message = "Backup chỉ chạy trên VPS Linux (thiếu deploy/backup-vps.sh)."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            _finish_run_notify(db, run)
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        env = os.environ.copy()
        env["BACKUP_ROOT"] = str(backup_root_dir())
        keep = run.keep_count if run.keep_count is not None else DEFAULT_KEEP_COUNT
        env["BACKUP_KEEP_COUNT"] = str(keep)
        env["BACKUP_RETENTION_DAYS"] = "0"
        if run.include_cache:
            env["BACKUP_INCLUDE_CACHE"] = "1"
        env["BACKUP_SKIP_DRIVE_UPLOAD"] = "1"

        proc = subprocess.run(
            ["bash", str(BACKUP_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=3600,
            check=False,
        )
        log_tail = (proc.stdout or "")[-4000:]
        if proc.stderr:
            log_tail = ((proc.stderr or "")[-2000:] + "\n" + log_tail)[-4000:]
        run.log_tail = log_tail or None

        if proc.returncode != 0:
            run.status = "failed"
            run.error_message = f"backup-vps.sh exit {proc.returncode}"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            _finish_run_notify(db, run)
            return

        archive = _find_newest_archive(started_ts)
        if archive and archive.is_file():
            run.archive_filename = archive.name
            run.archive_path = str(archive)
            run.archive_size_bytes = archive.stat().st_size
            from app.services.vps_backup_drive import upload_backup_archive

            drv_status, drv_link, drv_err = upload_backup_archive(archive)
            run.drive_upload_status = drv_status
            run.drive_web_link = drv_link
            run.drive_upload_error = drv_err
        else:
            run.drive_upload_status = "skipped"
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        _finish_run_notify(db, run)
    except subprocess.TimeoutExpired:
        run = db.query(VpsBackupRun).filter(VpsBackupRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = "Backup quá 60 phút — đã hủy."
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            _finish_run_notify(db, run)
    except Exception as exc:
        logger.exception("VPS backup run %s failed", run_id)
        run = db.query(VpsBackupRun).filter(VpsBackupRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            _finish_run_notify(db, run)
    finally:
        db.close()
        with _backup_job_lock:
            _backup_job_running = False


def is_backup_job_running() -> bool:
    with _backup_job_lock:
        return _backup_job_running


def queue_backup_run(
    db: Session,
    *,
    trigger: str,
    include_cache: Optional[bool] = None,
) -> VpsBackupRun:
    global _backup_job_running
    if not is_backup_environment_available():
        raise ValueError("Backup chỉ khả dụng trên VPS Linux.")

    with _backup_job_lock:
        if _backup_job_running:
            raise RuntimeError("Đang có một backup khác chạy. Vui lòng đợi hoàn tất.")
        _backup_job_running = True

    settings = get_or_create_settings(db)
    run = VpsBackupRun(
        trigger=trigger,
        status="queued",
        keep_count=effective_keep_count(settings),
        retention_days=effective_keep_count(settings),
        include_cache=bool(include_cache if include_cache is not None else settings.include_cache),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    thread = threading.Thread(
        target=_execute_backup_run,
        args=(run.id,),
        daemon=True,
        name=f"vps-backup-run-{run.id}",
    )
    thread.start()
    return run


def list_runs(db: Session, *, skip: int = 0, limit: int = 50) -> Tuple[int, List[VpsBackupRun]]:
    q = db.query(VpsBackupRun)
    total = q.count()
    rows = q.order_by(VpsBackupRun.created_at.desc()).offset(skip).limit(limit).all()
    return total, rows


def run_to_item(row: VpsBackupRun) -> dict:
    return {
        "id": row.id,
        "trigger": row.trigger,
        "status": row.status,
        "archive_filename": row.archive_filename,
        "archive_path": row.archive_path,
        "archive_size_bytes": row.archive_size_bytes,
        "archive_size_pretty": pretty_bytes(row.archive_size_bytes),
        "keep_count": row.keep_count,
        "include_cache": bool(row.include_cache),
        "error_message": row.error_message,
        "drive_upload_status": row.drive_upload_status,
        "drive_web_link": row.drive_web_link,
        "drive_upload_error": row.drive_upload_error,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "created_at": row.created_at,
    }


def list_archives(db: Session) -> Tuple[int, int, List[dict]]:
    root = backup_root_dir()
    if not root.is_dir():
        return 0, 0, []

    runs_by_name = {
        r.archive_filename: r.id
        for r in db.query(VpsBackupRun).filter(VpsBackupRun.archive_filename.isnot(None)).all()
        if r.archive_filename
    }

    items: List[dict] = []
    total_bytes = 0
    for p in sorted(root.glob("backup-188-*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file() or not ARCHIVE_RE.match(p.name):
            continue
        st = p.stat()
        total_bytes += st.st_size
        items.append(
            {
                "filename": p.name,
                "path": str(p),
                "size_bytes": st.st_size,
                "size_pretty": pretty_bytes(st.st_size),
                "modified_at": datetime.fromtimestamp(st.st_mtime),
                "linked_run_id": runs_by_name.get(p.name),
            }
        )
    return len(items), total_bytes, items


def delete_archive(filename: str) -> bool:
    path = resolve_archive_path(filename)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _same_schedule_minute(a: Optional[datetime], b: datetime) -> bool:
    if not a:
        return False
    return (
        a.year == b.year
        and a.month == b.month
        and a.day == b.day
        and a.hour == b.hour
        and a.minute == b.minute
    )


def scheduler_tick() -> None:
    if not is_backup_environment_available():
        return
    if is_backup_job_running():
        return

    db = SessionLocal()
    try:
        settings = get_or_create_settings(db)
        if not settings.enabled:
            return

        now = datetime.now()
        if now.weekday() not in normalize_days_of_week(settings.days_of_week):
            return
        if now.hour != int(settings.hour) or now.minute != int(settings.minute):
            return
        if _same_schedule_minute(settings.last_triggered_at, now):
            return

        queue_backup_run(db, trigger="scheduled")
        settings.last_triggered_at = now
        db.commit()
        logger.info("VPS backup scheduled run queued at %s", now.isoformat())
    except RuntimeError:
        logger.info("VPS backup schedule skipped — job already running")
    except Exception:
        logger.exception("VPS backup scheduler tick failed")
        db.rollback()
    finally:
        db.close()


def _scheduler_loop(interval_seconds: float) -> None:
    while True:
        try:
            scheduler_tick()
        except Exception:
            logger.exception("VPS backup scheduler loop error")
        time.sleep(max(30.0, float(interval_seconds)))


def start_vps_backup_scheduler_daemon_if_enabled() -> None:
    """Kiểm tra lịch backup mỗi 60s (bật khi VPS_BACKUP_SCHEDULER_ENABLED≠0)."""
    enabled = str(os.getenv("VPS_BACKUP_SCHEDULER_ENABLED", "1")).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not enabled:
        return
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(
        target=_scheduler_loop,
        args=(60.0,),
        daemon=True,
        name="vps-backup-scheduler",
    ).start()
