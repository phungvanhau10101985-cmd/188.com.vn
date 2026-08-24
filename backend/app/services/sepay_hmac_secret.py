"""Secret HMAC-SHA256 webhook SePay — lưu từ admin (file JSON, không cần restart)."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_FILENAME = "sepay-hmac-secret.json"
_MIN_SECRET = 8


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def secret_file() -> Path:
    return backend_root() / _FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_unlocked() -> dict[str, Any]:
    path = secret_file()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Không đọc được %s: %s", path.name, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _save_unlocked(payload: dict[str, Any]) -> None:
    path = secret_file()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_admin_secret() -> str:
    with _LOCK:
        raw = str(_load_unlocked().get("secret_key") or "").strip()
    return raw


def resolve_secret() -> str:
    """Ưu tiên key dán trên admin; không có thì dùng SEPAY_SECRET_KEY trong .env."""
    stored = get_admin_secret()
    if stored:
        return stored
    from app.core.config import settings

    return (getattr(settings, "SEPAY_SECRET_KEY", "") or "").strip()


def _env_secret() -> str:
    from app.core.config import settings

    return (getattr(settings, "SEPAY_SECRET_KEY", "") or "").strip()


def _mask_last4(value: str) -> str:
    v = (value or "").strip()
    if len(v) >= 4:
        return v[-4:]
    return v


def status_for_admin() -> dict[str, Any]:
    admin = get_admin_secret()
    env = _env_secret()
    effective = admin or env
    updated_at = ""
    with _LOCK:
        updated_at = str(_load_unlocked().get("updated_at") or "")
    source: Optional[str] = "admin" if admin else ("env" if env else None)
    return {
        "configured": bool(effective),
        "source": source,
        "last4": _mask_last4(effective) if effective else "",
        "updated_at": updated_at if admin else "",
        "admin_configured": bool(admin),
        "env_configured": bool(env),
    }


def save_secret(secret_key: str) -> dict[str, Any]:
    clean = (secret_key or "").strip()
    if len(clean) < _MIN_SECRET:
        raise ValueError(f"Secret Key phải dài ít nhất {_MIN_SECRET} ký tự.")
    payload = {"secret_key": clean, "updated_at": _now_iso()}
    with _LOCK:
        try:
            _save_unlocked(payload)
        except OSError as exc:
            raise ValueError(f"Không lưu được Secret Key: {exc}") from exc
    return status_for_admin()


def clear_secret() -> dict[str, Any]:
    path = secret_file()
    with _LOCK:
        if path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                raise ValueError(f"Không xóa được Secret Key: {exc}") from exc
    return status_for_admin()
