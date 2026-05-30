"""CRUD job bản địa hóa ảnh (PostgreSQL / SQLite)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.image_localization_job import ImageLocalizationJob

_TERMINAL = frozenset({"done", "error", "cancelled"})
_RESUMABLE = frozenset({"queued", "running"})


def get_job(db: Session, job_id: str) -> Optional[ImageLocalizationJob]:
    return db.query(ImageLocalizationJob).filter(ImageLocalizationJob.job_id == job_id).first()


def create_job(db: Session, job_id: str, initial: Dict[str, Any]) -> ImageLocalizationJob:
    row = ImageLocalizationJob(job_id=job_id, **initial)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_job(db: Session, job_id: str, updates: Dict[str, Any]) -> Optional[ImageLocalizationJob]:
    row = get_job(db, job_id)
    if not row:
        return None
    for key, val in updates.items():
        if hasattr(row, key):
            setattr(row, key, val)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def list_resumable_jobs(db: Session, limit: int = 20) -> List[ImageLocalizationJob]:
    return (
        db.query(ImageLocalizationJob)
        .filter(ImageLocalizationJob.status.in_(tuple(_RESUMABLE)))
        .order_by(ImageLocalizationJob.created_at.asc())
        .limit(limit)
        .all()
    )


def list_jobs_for_admin_track(
    db: Session,
    *,
    limit: int = 20,
    active_only: bool = False,
) -> List[ImageLocalizationJob]:
    """Job đang chạy + gần đây — admin khôi phục Tiến trình sau reload tab."""
    active_statuses = tuple(_RESUMABLE)
    if active_only:
        return (
            db.query(ImageLocalizationJob)
            .filter(ImageLocalizationJob.status.in_(active_statuses))
            .order_by(ImageLocalizationJob.created_at.desc())
            .limit(max(1, limit))
            .all()
        )

    active = (
        db.query(ImageLocalizationJob)
        .filter(ImageLocalizationJob.status.in_(active_statuses))
        .order_by(ImageLocalizationJob.created_at.desc())
        .all()
    )
    remaining = max(0, limit - len(active))
    if remaining <= 0:
        return active[:limit]

    active_ids = {row.job_id for row in active}
    terminal = (
        db.query(ImageLocalizationJob)
        .filter(~ImageLocalizationJob.status.in_(active_statuses))
        .order_by(ImageLocalizationJob.updated_at.desc())
        .limit(remaining + len(active_ids))
        .all()
    )
    out = list(active)
    for row in terminal:
        if row.job_id in active_ids:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def row_to_job_dict(row: ImageLocalizationJob) -> Dict[str, Any]:
    """Dict API giống job in-memory (admin poll)."""
    d: Dict[str, Any] = {
        "job_id": row.job_id,
        "status": row.status,
        "phase": row.phase,
        "message": row.message,
        "current": row.current,
        "total": row.total,
        "done": row.done,
        "failed": row.failed,
        "skipped": row.skipped,
        "percent": row.percent,
        "current_product_id": row.current_product_id,
        "cancel_requested": bool(row.cancel_requested),
        "language": row.language,
        "force": row.force,
        "dry_run": row.dry_run,
        "gemini_mode": row.gemini_mode,
        "local_image_only": row.local_image_only,
        "job_queue_product_ids": list(row.queue_product_ids or [])[:400],
        "job_queue_truncated": bool(row.job_queue_truncated),
        "skipped_product_reports": list(row.skipped_product_reports or []),
        "recent_results": list(row.recent_results or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "resume_count": row.resume_count or 0,
    }
    payload = row.payload if isinstance(row.payload, dict) else {}
    for key in (
        "gemini_image_model",
        "gemini_image_size",
        "openai_image_model",
        "openai_image_quality",
        "openai_image_size",
        "inference_tier",
        "allow_ai_image_models",
        "ai_image_explicit_only",
        "playwright_headless_requested",
        "playwright_headless_effective",
    ):
        if key in payload:
            d[key] = payload[key]
    return d


def delete_terminal_jobs(db: Session) -> tuple[int, List[str]]:
    """Xóa job đã kết thúc (done / error / cancelled)."""
    rows = (
        db.query(ImageLocalizationJob)
        .filter(ImageLocalizationJob.status.in_(tuple(_TERMINAL)))
        .all()
    )
    ids = [row.job_id for row in rows]
    if not ids:
        return 0, []
    db.query(ImageLocalizationJob).filter(ImageLocalizationJob.job_id.in_(ids)).delete(
        synchronize_session=False
    )
    db.commit()
    return len(ids), ids


def delete_job(db: Session, job_id: str) -> bool:
    """Xóa một job đã kết thúc (done / error / cancelled)."""
    jid = (job_id or "").strip()
    if not jid:
        return False
    row = get_job(db, jid)
    if not row:
        return False
    if (row.status or "").strip().lower() not in _TERMINAL:
        return False
    db.delete(row)
    db.commit()
    return True


def sync_dict_to_row(db: Session, job_id: str, job: Dict[str, Any]) -> None:
    """Ghi snapshot job từ dict in-memory."""
    if not job:
        return
    row = get_job(db, job_id)
    if not row:
        return
    status = job.get("status")
    existing = (row.status or "").strip().lower()
    new_st = (str(status).strip().lower() if status else "")
    if status:
        if existing in _TERMINAL and new_st and new_st not in _TERMINAL:
            status = None
        else:
            row.status = str(status)
    for field in (
        "phase",
        "message",
        "current",
        "total",
        "done",
        "failed",
        "skipped",
        "percent",
        "current_product_id",
        "job_queue_truncated",
    ):
        if field in job:
            setattr(row, field, job[field])
    if "cancel_requested" in job:
        row.cancel_requested = bool(job["cancel_requested"])
    if "queue_product_ids" in job:
        row.queue_product_ids = list(job["queue_product_ids"] or [])
    elif "job_queue_product_ids" in job:
        row.queue_product_ids = list(job["job_queue_product_ids"] or [])
    if "processed_product_ids" in job:
        row.processed_product_ids = list(job["processed_product_ids"] or [])
    if "recent_results" in job:
        row.recent_results = list(job["recent_results"] or [])[-100:]
    if "skipped_product_reports" in job:
        row.skipped_product_reports = list(job["skipped_product_reports"] or [])[-400:]
    if "language" in job:
        row.language = job.get("language")
    if "force" in job:
        row.force = bool(job.get("force"))
    if "dry_run" in job:
        row.dry_run = bool(job.get("dry_run"))
    if "gemini_mode" in job:
        row.gemini_mode = job.get("gemini_mode")
    if "local_image_only" in job:
        row.local_image_only = bool(job.get("local_image_only"))
    if job.get("started_at") and not row.started_at:
        row.started_at = datetime.now(timezone.utc)
    if status in _TERMINAL:
        row.finished_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
