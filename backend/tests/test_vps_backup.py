"""Unit tests — VPS backup admin API, notify HTML, Drive error messages."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import vps_backup_drive as drive_mod
from app.services import vps_backup_notify as notify_mod
from app.services import vps_backup_service as backup_svc


class HttpErrorStub(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


def test_format_drive_error_access_not_configured():
    exc = HttpErrorStub(
        'Google Drive API has not been used in project 297041609375 before or it is disabled. '
        'Reason: accessNotConfigured'
    )
    msg = drive_mod._format_drive_upload_error(exc)
    assert "297041609375" in msg
    assert "Google Drive API" in msg


def test_format_drive_error_folder_not_found():
    exc = HttpErrorStub(
        'File not found: 1NF152YF63m-jk_5tb3AlGnzAtPEcaYYu. Details: notFound'
    )
    with patch.object(
        drive_mod.settings,
        "VPS_BACKUP_DRIVE_FOLDER_ID",
        "1NF152YF63m-jk_5tb3AlGnzAtPEcaYYu",
    ):
        msg = drive_mod._format_drive_upload_error(exc)
    assert "1NF152YF63m-jk_5tb3AlGnzAtPEcaYYu" in msg
    assert "VPS_BACKUP_DRIVE_FOLDER_ID" in msg
    assert "Share folder" in msg or "share" in msg.lower()


def test_format_drive_error_storage_quota_service_account():
    exc = HttpErrorStub(
        'Service Accounts do not have storage quota. Leverage shared drives. '
        'reason: storageQuotaExceeded'
    )
    msg = drive_mod._format_drive_upload_error(exc)
    assert "Shared drive" in msg or "Ổ dung chung" in msg
    assert "Workspace" in msg or "VPS_BACKUP_DRIVE_ENABLED" in msg


def test_validate_folder_rejects_my_drive():
    service = SimpleNamespace()

    def fake_get(**kwargs):
        return SimpleNamespace(execute=lambda: {"id": "f1", "name": "MyFolder", "driveId": None, "capabilities": {"canAddChildren": True}})

    service.files = lambda: SimpleNamespace(get=fake_get)
    msg = drive_mod._validate_folder_for_service_account_upload(service, "f1")
    assert msg is not None
    assert "My Drive" in msg or "Drive cá nhân" in msg


def test_notify_module_imports_and_builds_html_without_fstring_backslash_issue():
    """Regression: Python 3.11 rejects backslashes inside f-string {...} expressions."""
    importlib.reload(notify_mod)
    assert notify_mod._send_email_task is not None

    sent: list[tuple] = []

    def fake_send(to: str, subject: str, text: str, html: str) -> None:
        sent.append((to, subject, text, html))

    with patch.object(notify_mod.settings, "VPS_BACKUP_NOTIFY_ENABLED", True), patch.object(
        notify_mod, "_recipient_emails", return_value=["admin@188.com.vn"]
    ), patch.object(notify_mod.settings, "is_smtp_configured", return_value=True), patch(
        "app.services.email_service.send_email", fake_send
    ):
        notify_mod._send_email_task(
            run_id=99,
            status="success",
            trigger="manual",
            archive_filename="backup-188-20260618-120000.tar.gz",
            archive_size_pretty="94.4 MB",
            error_message=None,
            drive_upload_status="failed",
            drive_upload_error="File not found: bad-folder-id",
        )

    assert len(sent) == 1
    _to, _subject, text_body, html_body = sent[0]
    assert "backup-188-20260618-120000.tar.gz" in text_body
    assert "Google Drive" in html_body
    assert "bad-folder-id" in html_body
    assert "\\" not in html_body.split("<p><b>Google Drive")[-1][:80]


def test_vps_backup_routes_registered_in_main_app():
    from main import app

    paths = sorted(
        r.path for r in app.routes if getattr(r, "path", None) and "/admin/vps-backup/" in r.path
    )
    assert "/api/v1/admin/vps-backup/settings" in paths
    assert "/api/v1/admin/vps-backup/run" in paths
    assert "/api/v1/admin/vps-backup/archives" in paths


def test_settings_payload_dev_backup_unavailable():
    row = SimpleNamespace(
        enabled=False,
        hour=3,
        minute=0,
        days_of_week=[0, 1, 2, 3, 4, 5, 6],
        keep_count=2,
        include_cache=False,
        last_triggered_at=None,
        updated_at=None,
    )
    with patch.object(backup_svc, "is_backup_environment_available", return_value=False), patch.object(
        drive_mod, "drive_settings_payload", return_value={"drive_upload_enabled": False}
    ):
        payload = backup_svc.settings_to_payload(row)
    assert payload["backup_available"] is False
    assert payload["keep_count"] == 2


def test_normalize_days_of_week_dedupes_and_sorts():
    assert backup_svc.normalize_days_of_week([6, 0, 6, 3]) == [0, 3, 6]


def test_pretty_bytes():
    assert backup_svc.pretty_bytes(1024) == "1.0 KB"
    assert backup_svc.pretty_bytes(None) == "—"
