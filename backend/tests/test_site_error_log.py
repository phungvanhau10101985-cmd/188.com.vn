"""Gom lỗi theo ngày và gửi email admin tối đa một lần cho mỗi lỗi."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.site_error_log import SiteErrorLog
from app.services import site_error_log as svc


def _session():
    engine = create_engine("sqlite:///:memory:")
    SiteErrorLog.__table__.create(engine)
    return sessionmaker(bind=engine)()


def _now():
    return datetime(2026, 10, 15, 3, 0, tzinfo=timezone.utc)


def test_same_error_emails_once_per_day(monkeypatch):
    db = _session()
    sent = []
    svc._email_backoff.clear()
    monkeypatch.setattr(svc, "_deliver_alert", lambda row, now: sent.append(row.id) or True)

    first = svc.record_site_error(
        source="server",
        message="payment failed for order 12345",
        exc_type="RuntimeError",
        location="app/services/pay.py:40",
        path="/api/v1/orders/12345",
        db=db,
        now=_now(),
    )
    second = svc.record_site_error(
        source="server",
        message="payment failed for order 999",
        exc_type="RuntimeError",
        location="app/services/pay.py:40",
        path="/api/v1/orders/999",
        db=db,
        now=_now() + timedelta(minutes=5),
    )

    assert first["emailed"] is True
    assert second["emailed"] is False
    assert second["occurrence_count"] == 2
    assert first["fingerprint"] == second["fingerprint"]
    assert len(sent) == 1
    db.close()


def test_next_day_sends_again(monkeypatch):
    db = _session()
    sent = []
    svc._email_backoff.clear()
    monkeypatch.setattr(svc, "_deliver_alert", lambda row, now: sent.append(row.id) or True)
    kwargs = dict(
        source="server",
        message="db down",
        exc_type="OperationalError",
        location="app/db/session.py:12",
        db=db,
    )
    svc.record_site_error(**kwargs, now=_now())
    again = svc.record_site_error(**kwargs, now=_now() + timedelta(days=1))
    assert again["emailed"] is True
    assert len(sent) == 2
    db.close()


def test_web_error_is_stored_without_email(monkeypatch):
    db = _session()
    sent = []
    monkeypatch.setattr(svc, "_deliver_alert", lambda row, now: sent.append(1) or True)
    result = svc.record_site_error(
        source="web",
        message="Cannot read properties of undefined",
        location="https://188.com.vn/app.js",
        path="/cart",
        db=db,
        now=_now(),
    )
    assert result["emailed"] is False
    assert result["skipped"] is False
    assert sent == []
    assert db.query(SiteErrorLog).count() == 1
    db.close()


def test_client_noise_skipped():
    db = _session()
    result = svc.record_site_error(
        source="web",
        message="ResizeObserver loop completed with undelivered notifications.",
        db=db,
        now=_now(),
    )
    assert result["skipped"] is True
    assert db.query(SiteErrorLog).count() == 0
    db.close()


def test_web_server_source_emails(monkeypatch):
    db = _session()
    sent = []
    svc._email_backoff.clear()
    monkeypatch.setattr(svc, "_deliver_alert", lambda row, now: sent.append(row.source) or True)
    result = svc.record_site_error(
        source="web_server",
        message="digest boom",
        location="app/cart/page.tsx",
        db=db,
        now=_now(),
    )
    assert result["emailed"] is True
    assert sent == ["web_server"]
    db.close()


def test_untrusted_report_cannot_mark_itself_server(monkeypatch):
    monkeypatch.setattr(svc.settings, "SITE_ERROR_INGEST_SECRET", "secret-token")
    assert svc.resolve_report_source(kind="web_server", token="secret-token") == "web_server"
    assert svc.resolve_report_source(kind="web_server", token="nope") == "web"
    assert svc.resolve_report_source(kind="server", token="secret-token") == "web"


def test_handler_ignores_info_and_own_logger():
    info = logging_record(logging.INFO, "app.api.orders", "nope")
    error = logging_record(logging.ERROR, "app.api.orders", "boom")
    own = logging_record(logging.ERROR, "app.services.site_error_log", "boom")
    uvicorn = logging_record(logging.ERROR, "uvicorn.error", "Exception in ASGI application")
    assert svc.should_capture_record(info) is False
    assert svc.should_capture_record(error) is True
    assert svc.should_capture_record(own) is False
    assert svc.should_capture_record(uvicorn) is False


def logging_record(level: int, name: str, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="app/api/orders.py",
        lineno=10,
        msg=message,
        args=(),
        exc_info=None,
    )
