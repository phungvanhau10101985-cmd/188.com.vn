"""Job bản địa hóa không được chết khi Postgres cắt connection lúc chờ RAM."""

from sqlalchemy.exc import OperationalError

from app.api.endpoints import image_localization as jobs


class _DeadSession:
    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def expunge(self, _obj) -> None:
        return None


def _ssl_closed() -> OperationalError:
    return OperationalError(
        "SELECT",
        {},
        Exception("SSL connection has been closed unexpectedly"),
    )


def test_dropped_db_connection_does_not_cancel_waiting_job(monkeypatch):
    def raise_ssl(_db, _job_id):
        raise _ssl_closed()

    monkeypatch.setattr(jobs.image_loc_job_crud, "get_job", raise_ssl)
    monkeypatch.setattr(jobs, "SessionLocal", lambda: _DeadSession())
    with jobs._jobs_lock:
        jobs._jobs["job-wait"] = {"job_id": "job-wait", "status": "running"}
    try:
        assert jobs._job_get("job-wait").get("status") == "running"
        assert jobs._job_cancel_signal("job-wait") is False
        assert jobs._jobs["job-wait"]["status"] == "running"
    finally:
        with jobs._jobs_lock:
            jobs._jobs.pop("job-wait", None)
