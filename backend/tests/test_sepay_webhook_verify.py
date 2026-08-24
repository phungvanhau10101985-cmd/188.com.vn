"""Unit tests — verify_webhook HMAC-SHA256 SePay ({timestamp}.{body} + sha256=)."""

import hashlib
import hmac

from starlette.requests import Request

import pytest

from app.core.config import settings
from app.services import sepay_hmac_secret as hmac_svc
from app.services.sepay import verify_webhook

_SECRET = "test-sepay-secret"
_SEPAY_IP = "172.236.138.20"
_BODY = b'{"id":1,"transferAmount":10000}'


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    message = f"{timestamp}.".encode("utf-8") + body
    return "sha256=" + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _request(
    *,
    headers: dict[str, str] | None = None,
    client_host: str = _SEPAY_IP,
    query: str = "",
) -> Request:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/sepay/webhook",
            "headers": raw_headers,
            "query_string": query.encode("utf-8"),
            "client": (client_host, 443),
        }
    )


@pytest.fixture(autouse=True)
def isolate_admin_hmac_file(tmp_path, monkeypatch):
    monkeypatch.setattr(hmac_svc, "secret_file", lambda: tmp_path / "sepay-hmac-secret.json")


def _secure_settings(monkeypatch, **overrides):
    defaults = {
        "SEPAY_SECRET_KEY": _SECRET,
        "SEPAY_WEBHOOK_API_KEY": "",
        "SEPAY_WEBHOOK_PUBLIC_URL": "",
        "SEPAY_ALLOW_INSECURE_DEV": False,
        "SEPAY_WEBHOOK_TRUST_NO_AUTH_IP": True,
        "SEPAY_REQUIRE_SIGNATURE": False,
        "SEPAY_WEBHOOK_IP_ALLOWLIST": frozenset({_SEPAY_IP}),
        "SEPAY_WEBHOOK_TRUST_PROXY_HEADERS": False,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def test_hmac_accepts_timestamp_dot_raw_body(monkeypatch):
    _secure_settings(monkeypatch)
    ts = "1710000000"
    req = _request(headers={"X-SePay-Signature": _sign(_SECRET, ts, _BODY), "X-SePay-Timestamp": ts})
    assert verify_webhook(req, _BODY) is True


def test_hmac_rejects_wrong_signature(monkeypatch):
    _secure_settings(monkeypatch)
    ts = "1710000000"
    req = _request(
        headers={"X-SePay-Signature": "sha256=" + ("ab" * 32), "X-SePay-Timestamp": ts},
        client_host=_SEPAY_IP,
    )
    assert verify_webhook(req, _BODY) is False


def test_hmac_rejects_body_only_legacy_mac(monkeypatch):
    """Chữ ký cũ (HMAC raw body, không timestamp / không sha256=) phải bị từ chối."""
    _secure_settings(monkeypatch)
    ts = "1710000000"
    legacy_hex = hmac.new(_SECRET.encode("utf-8"), _BODY, hashlib.sha256).hexdigest()
    req = _request(headers={"X-SePay-Signature": legacy_hex, "X-SePay-Timestamp": ts})
    assert verify_webhook(req, _BODY) is False


def test_hmac_rejects_missing_timestamp(monkeypatch):
    _secure_settings(monkeypatch)
    ts = "1710000000"
    req = _request(headers={"X-SePay-Signature": _sign(_SECRET, ts, _BODY)})
    assert verify_webhook(req, _BODY) is False


def test_bad_hmac_does_not_fall_through_to_ip(monkeypatch):
    _secure_settings(monkeypatch)
    ts = "1710000000"
    req = _request(
        headers={"X-SePay-Signature": "sha256=" + ("cd" * 32), "X-SePay-Timestamp": ts},
        client_host=_SEPAY_IP,
    )
    assert verify_webhook(req, _BODY) is False


def test_valid_hmac_accepts_even_if_ip_not_in_allowlist(monkeypatch):
    _secure_settings(monkeypatch)
    ts = "1710000000"
    req = _request(
        headers={"X-SePay-Signature": _sign(_SECRET, ts, _BODY), "X-SePay-Timestamp": ts},
        client_host="8.8.8.8",
    )
    assert verify_webhook(req, _BODY) is True


def test_ip_allowlist_is_secondary_when_no_hmac(monkeypatch):
    _secure_settings(monkeypatch)
    req = _request(client_host=_SEPAY_IP)
    assert verify_webhook(req, _BODY) is True


def test_ip_allowlist_rejects_unknown_ip_without_hmac(monkeypatch):
    _secure_settings(monkeypatch)
    req = _request(client_host="8.8.8.8")
    assert verify_webhook(req, _BODY) is False


def test_api_key_still_works_without_hmac(monkeypatch):
    _secure_settings(monkeypatch, SEPAY_WEBHOOK_API_KEY="hook-token", SEPAY_WEBHOOK_TRUST_NO_AUTH_IP=False)
    req = _request(headers={"Authorization": "Apikey hook-token"}, client_host="8.8.8.8")
    assert verify_webhook(req, _BODY) is True


def test_admin_stored_secret_overrides_env(monkeypatch):
    _secure_settings(monkeypatch)
    hmac_svc.save_secret("whsec_from_admin_form")
    ts = "1710000000"
    req = _request(
        headers={
            "X-SePay-Signature": _sign("whsec_from_admin_form", ts, _BODY),
            "X-SePay-Timestamp": ts,
        }
    )
    assert verify_webhook(req, _BODY) is True
    env_signed = _request(
        headers={"X-SePay-Signature": _sign(_SECRET, ts, _BODY), "X-SePay-Timestamp": ts}
    )
    assert verify_webhook(env_signed, _BODY) is False
