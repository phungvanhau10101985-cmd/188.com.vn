"""Key partner tra cứu vận chuyển — cấp từ admin, lưu file JSON (không cần restart)."""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_FILENAME = "shipping-lookup-keys.json"
_MAX_LABEL = 80
_MIN_PASTED_TOKEN = 16


def backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def keys_file() -> Path:
    return backend_root() / _FILENAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _public_row(item: dict[str, Any]) -> dict[str, Any]:
    token = str(item.get("token") or "")
    last4 = token[-4:] if len(token) >= 4 else token
    return {
        "id": str(item.get("id") or ""),
        "label": str(item.get("label") or ""),
        "last4": last4,
        "created_at": str(item.get("created_at") or ""),
    }


def _load_unlocked() -> list[dict[str, Any]]:
    path = keys_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Không đọc được %s: %s", path.name, exc)
        return []
    raw = data.get("keys") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        kid = str(item.get("id") or "").strip()
        if not token or not kid:
            continue
        out.append(
            {
                "id": kid,
                "label": str(item.get("label") or "").strip(),
                "token": token,
                "created_at": str(item.get("created_at") or ""),
            }
        )
    return out


def _save_unlocked(items: list[dict[str, Any]]) -> None:
    path = keys_file()
    payload = {"keys": items}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_issued_keys() -> list[dict[str, Any]]:
    with _LOCK:
        return _load_unlocked()


def issued_tokens() -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for item in load_issued_keys():
        token = str(item.get("token") or "").strip()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def list_for_admin() -> dict[str, Any]:
    rows = [_public_row(item) for item in load_issued_keys()]
    return {"keys": rows}


def create_key(label: str, token: Optional[str] = None) -> dict[str, Any]:
    clean_label = (label or "").strip()
    if not clean_label:
        raise ValueError("Nhập tên đối tác / nhãn key.")
    if len(clean_label) > _MAX_LABEL:
        raise ValueError(f"Nhãn tối đa {_MAX_LABEL} ký tự.")

    pasted = (token or "").strip()
    if pasted:
        if len(pasted) < _MIN_PASTED_TOKEN:
            raise ValueError(f"Key dán vào phải dài ít nhất {_MIN_PASTED_TOKEN} ký tự.")
        new_token = pasted
    else:
        new_token = secrets.token_hex(32)

    item = {
        "id": str(uuid.uuid4()),
        "label": clean_label,
        "token": new_token,
        "created_at": _now_iso(),
    }
    with _LOCK:
        items = _load_unlocked()
        if any(str(existing.get("token") or "") == new_token for existing in items):
            raise ValueError("Key này đã có trên danh sách cấp phát.")
        items.append(item)
        try:
            _save_unlocked(items)
        except OSError as exc:
            raise ValueError(f"Không lưu được file key: {exc}") from exc
    public = _public_row(item)
    public["token"] = new_token
    return public


def get_key_token(key_id: str) -> dict[str, Any]:
    kid = (key_id or "").strip()
    for item in load_issued_keys():
        if str(item.get("id") or "") == kid:
            public = _public_row(item)
            public["token"] = str(item.get("token") or "")
            return public
    raise KeyError("Không tìm thấy key.")


def revoke_key(key_id: str) -> dict[str, Any]:
    kid = (key_id or "").strip()
    if not kid:
        raise KeyError("Không tìm thấy key.")
    with _LOCK:
        items = _load_unlocked()
        kept = [item for item in items if str(item.get("id") or "") != kid]
        if len(kept) == len(items):
            raise KeyError("Không tìm thấy key.")
        try:
            _save_unlocked(kept)
        except OSError as exc:
            raise ValueError(f"Không lưu được file key: {exc}") from exc
    return {"ok": True, "id": kid}
