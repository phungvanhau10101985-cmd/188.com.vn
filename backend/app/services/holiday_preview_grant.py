"""Mã xem trước giao diện lễ, dùng khi admin và cửa hàng là hai host."""

from __future__ import annotations

import hashlib
import hmac
import time

from app.core.config import settings
from app.services.holiday_schedule import CATALOG

PREVIEW_TTL_SECONDS = 10 * 60


def _secret() -> bytes:
    return (settings.SECRET_KEY or "dev").encode("utf-8")


def issue_holiday_preview_token(code: str, *, now: int | None = None) -> tuple[str, int]:
    theme = (code or "").strip()
    if theme not in CATALOG:
        raise ValueError("Dịp lễ không có trong danh sách")
    issued = int(time.time() if now is None else now)
    expires_at = issued + PREVIEW_TTL_SECONDS
    payload = f"{theme}.{expires_at}"
    sig = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}", expires_at


def parse_holiday_preview_token(token: str, *, now: int | None = None) -> tuple[str, int] | None:
    raw = (token or "").strip()
    parts = raw.split(".")
    if len(parts) != 3:
        return None
    code, exp_text, sig = parts
    if code not in CATALOG or not exp_text.isdigit() or len(sig) != 32:
        return None
    payload = f"{code}.{exp_text}"
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, sig):
        return None
    expires_at = int(exp_text)
    current = int(time.time() if now is None else now)
    if current >= expires_at:
        return None
    return code, expires_at
