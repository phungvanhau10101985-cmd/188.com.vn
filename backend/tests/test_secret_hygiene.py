"""API key không được nằm trên URL Gemini hoặc trong log."""

from app.core.secret_hygiene import (
    bearer_matches,
    redact_database_url,
    redact_secrets,
    register_secret_values,
    secret_equals,
)
from app.services.gemini_http import GEMINI_API_KEY_HEADER, relocate_gemini_api_key


def test_secret_equals_rejects_empty_and_mismatch():
    assert secret_equals("abc", "abc") is True
    assert secret_equals(" abc ", "abc") is True
    assert secret_equals("", "abc") is False
    assert secret_equals("abc", "") is False
    assert secret_equals("abcd", "abc") is False
    assert secret_equals("abc", "abd") is False


def test_bearer_matches_scheme_only():
    assert bearer_matches("Bearer cron-secret", "cron-secret") is True
    assert bearer_matches("bearer cron-secret", "cron-secret") is True
    assert bearer_matches("Token cron-secret", "cron-secret") is False
    assert bearer_matches("Bearer wrong", "cron-secret") is False


def test_redact_query_header_and_known_secret():
    register_secret_values(["super-secret-value"])
    raw = (
        "https://example.test/hook?token=abc123&x=1 "
        "AIzaFAKEKEY1234567890ABCD "
        "Authorization: Bearer super-secret-value "
        "x-goog-api-key: another-gemini-key"
    )
    cleaned = redact_secrets(raw)
    assert "abc123" not in cleaned
    assert "AIzaFAKE" not in cleaned
    assert "super-secret-value" not in cleaned
    assert "another-gemini-key" not in cleaned
    assert "token=[redacted]" in cleaned


def test_redact_database_url_hides_password():
    shown = redact_database_url("postgresql://shop:s3cret@127.0.0.1:5432/store")
    assert "s3cret" not in shown
    assert "shop:[redacted]@127.0.0.1:5432/store" in shown


def test_relocate_gemini_key_from_query_and_params():
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaTestKey1234567890"
    clean, kwargs = relocate_gemini_api_key(url, {"params": {"key": "from-params-1234567890"}})
    assert "key=" not in clean
    assert "AIzaTestKey1234567890" not in clean
    assert kwargs["headers"][GEMINI_API_KEY_HEADER] == "from-params-1234567890"
    assert "params" not in kwargs


def test_relocate_leaves_non_gemini_params():
    url = "https://example.test/search?key=keep-me"
    clean, kwargs = relocate_gemini_api_key(url, {"params": {"key": "keep-me"}})
    assert clean == url
    assert kwargs["params"]["key"] == "keep-me"
