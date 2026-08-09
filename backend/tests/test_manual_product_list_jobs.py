"""list_jobs hiển thị phiên không có created_by (legacy) cho mọi admin."""

from app.services.manual_product_create_job_store import list_jobs, persist_job


def test_list_jobs_includes_legacy_jobs_without_owner(tmp_path, monkeypatch):
    job_id = "b2c3d4e5-f6a7-8901-bcde-f12345678901"
    root = tmp_path / "manual_product_jobs"
    root.mkdir()
    monkeypatch.setattr(
        "app.services.manual_product_create_job_store._jobs_root",
        lambda: root,
    )
    persist_job(
        job_id,
        {"job_id": job_id, "status": "awaiting_input", "payload": {"mode": "ai"}},
    )
    rows = list_jobs(active_only=True, limit=10, created_by=99)
    assert len(rows) == 1
    assert rows[0]["job_id"] == job_id


def test_list_jobs_excludes_other_admin_jobs(tmp_path, monkeypatch):
    job_id = "c3d4e5f6-a7b8-9012-cdef-123456789012"
    root = tmp_path / "manual_product_jobs"
    root.mkdir()
    monkeypatch.setattr(
        "app.services.manual_product_create_job_store._jobs_root",
        lambda: root,
    )
    persist_job(
        job_id,
        {
            "job_id": job_id,
            "status": "awaiting_input",
            "created_by": 2,
            "payload": {"mode": "ai"},
        },
    )
    rows = list_jobs(active_only=True, limit=10, created_by=1)
    assert rows == []
