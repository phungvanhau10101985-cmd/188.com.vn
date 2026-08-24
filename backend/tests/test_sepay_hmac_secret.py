"""Lưu / xóa Secret Key HMAC SePay từ form admin."""

from pathlib import Path

import pytest

from app.services import sepay_hmac_secret as hmac_svc


@pytest.fixture
def secret_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "sepay-hmac-secret.json"
    monkeypatch.setattr(hmac_svc, "secret_file", lambda: path)
    return path


def test_save_status_and_resolve(secret_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.core.config.settings.SEPAY_SECRET_KEY", "env-secret-key")
    assert hmac_svc.get_admin_secret() == ""
    assert hmac_svc.resolve_secret() == "env-secret-key"

    status = hmac_svc.save_secret("whsec_live_example_key")
    assert secret_path.is_file()
    assert status["configured"] is True
    assert status["source"] == "admin"
    assert status["last4"] == "_key"
    assert status["admin_configured"] is True
    assert "secret_key" not in status
    assert hmac_svc.resolve_secret() == "whsec_live_example_key"


def test_save_rejects_short_key(secret_path: Path):
    with pytest.raises(ValueError, match="8"):
        hmac_svc.save_secret("short")


def test_clear_falls_back_to_env(secret_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.core.config.settings.SEPAY_SECRET_KEY", "env-secret-key")
    hmac_svc.save_secret("whsec_admin_only")
    cleared = hmac_svc.clear_secret()
    assert not secret_path.exists()
    assert cleared["source"] == "env"
    assert hmac_svc.resolve_secret() == "env-secret-key"
