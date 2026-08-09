"""Xóa phiên manual product job dở."""

import json

import pytest

from app.services.manual_product_create_job_store import delete_job, load_job, persist_job
from app.services.manual_product_create_service import delete_manual_product_job


def test_delete_job_removes_file(tmp_path, monkeypatch):
    job_id = "f4a0ffd8-772c-494b-877d-24f7220223a7"
    root = tmp_path / "manual_product_jobs"
    root.mkdir()
    monkeypatch.setattr(
        "app.services.manual_product_create_job_store._jobs_root",
        lambda: root,
    )
    persist_job(job_id, {"job_id": job_id, "status": "awaiting_input"})
    assert load_job(job_id) is not None
    assert delete_job(job_id) is True
    assert load_job(job_id) is None


def test_delete_manual_product_job_checks_owner(tmp_path, monkeypatch):
    job_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    root = tmp_path / "manual_product_jobs"
    root.mkdir()
    monkeypatch.setattr(
        "app.services.manual_product_create_job_store._jobs_root",
        lambda: root,
    )
    persist_job(job_id, {"job_id": job_id, "status": "awaiting_input", "created_by": 1})
    delete_manual_product_job(job_id, created_by=1)
    assert load_job(job_id) is None

    persist_job(job_id, {"job_id": job_id, "status": "awaiting_input", "created_by": 2})
    with pytest.raises(ValueError, match="quyền"):
        delete_manual_product_job(job_id, created_by=1)
