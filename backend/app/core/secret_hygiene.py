"""So khớp và che API key / secret trước khi chúng rơi vào log, traceback, hoặc stdout."""

from __future__ import annotations

import hmac
import logging
import re
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

_MIN_REGISTERED = 8
_registered: list[str] = []
_installed = False

_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:key|api_key|apikey|access_token|refresh_token|client_secret|token|secret)=)[^&#\s\"']+"
)
_AIZA = re.compile(r"AIza[0-9A-Za-z_\-]{20,}")
_SK = re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")
_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_BEARER = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-+/=]{12,}")
_APIKEY_WORD = re.compile(r"(?i)\b(apikey\s+)[A-Za-z0-9._\-+/=]{8,}")
_HEADER_KEY = re.compile(
    r"(?i)(x-goog-api-key|x-api-key|x-broken-media-purge-key)(['\"]?\s*[:=]\s*['\"]?)[^\s'\"]+"
)

# Giá trị đọc từ Settings — đăng ký lúc startup, không import config ở đây.
_SECRET_ATTRS = (
    "SECRET_KEY",
    "CRON_SECRET",
    "BIRTHDAY_PROMO_CRON_SECRET",
    "FACEBOOK_CAPI_INGEST_SECRET",
    "BROKEN_MEDIA_PURGE_SECRET",
    "SITE_ERROR_INGEST_SECRET",
    "SEPAY_WEBHOOK_API_KEY",
    "SEPAY_SECRET_KEY",
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "BUNNY_STORAGE_ACCESS_KEY",
    "ZALO_OA_SECRET",
    "ZALO_OA_ACCESS_TOKEN",
    "ZALO_REFRESH_TOKEN",
    "FIREBASE_PRIVATE_KEY",
    "FIREBASE_API_KEY",
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "META_ADS_ACCESS_TOKEN",
    "NANOAI_EMBED_KEY",
    "NANOAI_BEARER_TOKEN",
    "EMS_MERCHANT_TOKEN",
    "SHIPPING_LOOKUP_API_KEY",
    "SMTP_PASS",
    "VAPID_PRIVATE_KEY",
    "DATABASE_URL",
)


def secret_equals(got: str | None, expected: str | None) -> bool:
    """So sánh secret theo thời gian gần như không đổi. Chuỗi rỗng luôn là không khớp."""
    a = (got or "").strip().encode("utf-8")
    b = (expected or "").strip().encode("utf-8")
    if not a or not b or len(a) != len(b):
        return False
    return hmac.compare_digest(a, b)


def bearer_matches(authorization: str | None, secret: str | None) -> bool:
    raw = (authorization or "").strip()
    if len(raw) < 7 or raw[:7].lower() != "bearer ":
        return False
    return secret_equals(raw[7:], secret)


def register_secret_values(values: Iterable[str | None]) -> None:
    for raw in values:
        text = (raw or "").strip()
        if len(text) < _MIN_REGISTERED or text in _registered:
            continue
        _registered.append(text)


def register_settings_secrets(settings_obj: object) -> None:
    values: list[str] = []
    for name in _SECRET_ATTRS:
        values.append(str(getattr(settings_obj, name, "") or ""))
    register_secret_values(values)
    db = str(getattr(settings_obj, "DATABASE_URL", "") or "")
    try:
        password = urlsplit(db).password or ""
    except Exception:
        password = ""
    if len(password) >= _MIN_REGISTERED:
        register_secret_values([password])


def redact_database_url(url: str | None) -> str:
    raw = url or ""
    if "://" not in raw:
        return raw
    try:
        parts = urlsplit(raw)
    except Exception:
        return "[redacted-database-url]"
    if parts.username is None and parts.password is None:
        return raw
    host = parts.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parts.port:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    netloc = f"{user}:[redacted]@{host}" if user else f"[redacted]@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def redact_secrets(text: str | None) -> str:
    if not text:
        return text or ""
    out = str(text)
    # Bản dài trước để không để sót đuôi sau khi cắt chuỗi ngắn hơn nằm trong nó.
    for secret in sorted(_registered, key=len, reverse=True):
        if secret and secret in out:
            out = out.replace(secret, "[redacted]")
    out = _PEM.sub("[redacted-private-key]", out)
    out = _QUERY_SECRET.sub(r"\1[redacted]", out)
    out = _HEADER_KEY.sub(r"\1\2[redacted]", out)
    out = _BEARER.sub(r"\1[redacted]", out)
    out = _APIKEY_WORD.sub(r"\1[redacted]", out)
    out = _AIZA.sub("[redacted]", out)
    out = _SK.sub("[redacted]", out)
    return out


def install_secret_log_redaction() -> None:
    """Che secret trong mọi log dùng logging.Formatter / LogRecord.getMessage."""
    global _installed
    if _installed:
        return

    original_get_message = logging.LogRecord.getMessage

    def get_message(self: logging.LogRecord) -> str:
        try:
            return redact_secrets(original_get_message(self))
        except Exception:
            return original_get_message(self)

    original_format = logging.Formatter.format

    def format_redacted(self: logging.Formatter, record: logging.LogRecord) -> str:
        rendered = original_format(self, record)
        try:
            return redact_secrets(rendered)
        except Exception:
            return rendered

    logging.LogRecord.getMessage = get_message  # type: ignore[method-assign]
    logging.Formatter.format = format_redacted  # type: ignore[method-assign]
    _installed = True
