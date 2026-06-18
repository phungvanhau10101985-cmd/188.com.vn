"""Admin API — lịch backup VPS, chạy tay & danh sách file backup."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.schemas.vps_backup_admin import (
    VpsBackupArchiveListResponse,
    VpsBackupDeleteArchiveResponse,
    VpsBackupRunListResponse,
    VpsBackupSettingsResponse,
    VpsBackupSettingsUpdate,
    VpsBackupTriggerResponse,
)
from app.services import vps_backup_service as backup_svc

router = APIRouter()


@router.get("/settings", response_model=VpsBackupSettingsResponse)
def get_vps_backup_settings(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    row = backup_svc.get_or_create_settings(db)
    return backup_svc.settings_to_payload(row)


@router.put("/settings", response_model=VpsBackupSettingsResponse)
def update_vps_backup_settings(
    payload: VpsBackupSettingsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    days = backup_svc.normalize_days_of_week(payload.days_of_week)
    if not days:
        raise HTTPException(status_code=400, detail="Chọn ít nhất một ngày trong tuần.")
    row = backup_svc.update_settings(
        db,
        {
            "enabled": payload.enabled,
            "hour": payload.hour,
            "minute": payload.minute,
            "days_of_week": days,
            "include_cache": payload.include_cache,
        },
    )
    return backup_svc.settings_to_payload(row)


@router.get("/runs", response_model=VpsBackupRunListResponse)
def list_vps_backup_runs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    total, rows = backup_svc.list_runs(db, skip=skip, limit=limit)
    return {
        "total": total,
        "items": [backup_svc.run_to_item(r) for r in rows],
    }


@router.get("/archives", response_model=VpsBackupArchiveListResponse)
def list_vps_backup_archives(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    total, total_bytes, items = backup_svc.list_archives(db)
    return {
        "total": total,
        "total_size_bytes": total_bytes,
        "total_size_pretty": backup_svc.pretty_bytes(total_bytes),
        "items": items,
    }


@router.get("/archives/{filename}/download")
def download_vps_backup_archive(
    filename: str,
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        path = backup_svc.resolve_archive_path(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy file backup.")
    return FileResponse(
        path=str(path),
        media_type="application/gzip",
        filename=path.name,
    )


@router.post("/run", response_model=VpsBackupTriggerResponse)
def trigger_vps_backup_manual(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        run = backup_svc.queue_backup_run(db, trigger="manual")
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "run_id": run.id,
        "status": run.status,
        "message": "Đã xếp hàng backup. Email sẽ gửi admin khi hoàn tất.",
    }


@router.delete("/archives/{filename}", response_model=VpsBackupDeleteArchiveResponse)
def delete_vps_backup_archive(
    filename: str,
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        deleted = backup_svc.delete_archive(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy file backup.")
    return {"deleted": True, "filename": filename}
