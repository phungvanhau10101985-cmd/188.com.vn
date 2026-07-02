"""Tuỳ chọn bản địa hóa ảnh do admin bật trên UI (persist JSON, không cần restart)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_prefs_cache: Dict[str, Any] | None = None


def _prefs_path() -> Path:
    root = Path(getattr(settings, "IMAGE_LOCALIZATION_RUNTIME_DIR", "") or "").expanduser()
    if not str(root).strip():
        root = Path(__file__).resolve().parents[2] / "runtime" / "image_localization"
    path = root / "admin_prefs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_prefs_unlocked() -> Dict[str, Any]:
    global _prefs_cache
    if _prefs_cache is not None:
        return dict(_prefs_cache)
    path = _prefs_path()
    if not path.is_file():
        _prefs_cache = {}
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        _prefs_cache = raw if isinstance(raw, dict) else {}
    except Exception as exc:
        logger.warning("image_localization admin_prefs read failed: %s", exc)
        _prefs_cache = {}
    return dict(_prefs_cache)


def _save_prefs_unlocked(data: Dict[str, Any]) -> None:
    global _prefs_cache
    path = _prefs_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _prefs_cache = dict(data)


def deepseek_off_peak_only_env_default() -> bool:
    return bool(getattr(settings, "IMAGE_LOCALIZATION_DEEPSEEK_OFF_PEAK_ONLY", False))


def deepseek_off_peak_only_effective() -> bool:
    with _lock:
        prefs = _load_prefs_unlocked()
    if "deepseek_off_peak_only" in prefs:
        return bool(prefs["deepseek_off_peak_only"])
    return deepseek_off_peak_only_env_default()


def deepseek_off_peak_only_runtime_overridden() -> bool:
    with _lock:
        prefs = _load_prefs_unlocked()
    return "deepseek_off_peak_only" in prefs


def set_deepseek_off_peak_only(enabled: bool) -> bool:
    with _lock:
        prefs = _load_prefs_unlocked()
        prefs["deepseek_off_peak_only"] = bool(enabled)
        _save_prefs_unlocked(prefs)
    return deepseek_off_peak_only_effective()
