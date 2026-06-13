"""Import Excel async job — cooperative cancel."""

from unittest.mock import patch

from app.services.import_excel_job_store import ImportExcelJobCancelled, persist_import_job


def test_import_job_cancel_requested_raises():
    from app.api.endpoints import import_export as mod

    job_id = "d53d8641-d966-4e2c-8ed7-f4c89618afe4"
    mod.IMPORT_EXCEL_JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "cancel_requested": True,
    }
    try:
        mod._import_job_check_cancel(job_id)
        assert False, "expected ImportExcelJobCancelled"
    except ImportExcelJobCancelled:
        pass
    finally:
        mod.IMPORT_EXCEL_JOBS.pop(job_id, None)


def test_cancel_endpoint_marks_job(tmp_path):
    from app.api.endpoints import import_export as mod

    job_id = "11111111-2222-3333-4444-555555555555"
    mod.IMPORT_EXCEL_JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "phase": "database",
        "current": 0,
        "total": 150,
        "message": "Đang ghi CSDL",
    }
    with patch.object(mod, "persist_import_job", persist_import_job):
        out = mod.cancel_import_excel_job(job_id, _=None)  # type: ignore[arg-type]
    assert out["cancel_requested"] is True
    assert "hủy" in (out.get("message") or "").lower()
    mod.IMPORT_EXCEL_JOBS.pop(job_id, None)
