"""Cổng thử một ảnh bản địa hóa. File nằm trong runtime và xóa sau 7 ngày."""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import sys
import time
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.image_localization_service import (
    GeminiApiImageAdapter,
    LegacyImageLocalizationPipeline,
    build_gemini_image_adapter,
)

logger = logging.getLogger(__name__)

TRIAL_TTL = timedelta(days=7)
MAX_TRIAL_BYTES = 12 * 1024 * 1024
_TRIAL_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_MODES = {"local_only", "api", "openai"}


def _write_jpeg_copy(path: Path, image_bytes: bytes) -> None:
    try:
        import cv2
        import numpy as np

        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is not None:
            ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if ok:
                path.write_bytes(encoded.tobytes())
                return
    except Exception:
        logger.debug("Không encode được JPEG xem trước", exc_info=True)
    path.write_bytes(image_bytes)


def trials_root() -> Path:
    root = Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR) / "trials"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def purge_expired_trials(now: Optional[datetime] = None) -> int:
    """Xóa thư mục thử quá 7 ngày. Trả số thư mục đã xóa."""
    moment = now or _now()
    removed = 0
    root = trials_root()
    for folder in root.iterdir():
        if not folder.is_dir() or not _TRIAL_ID_RE.match(folder.name):
            continue
        meta_path = folder / "meta.json"
        created = None
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                meta = {}
            created = _parse_iso(str(meta.get("created_at") or ""))
        if created is None:
            created = datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc)
        if moment - created >= TRIAL_TTL:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


def _read_meta(folder: Path) -> Optional[Dict[str, Any]]:
    path = folder / "meta.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _public_trial(meta: Dict[str, Any]) -> Dict[str, Any]:
    trial_id = str(meta.get("id") or "")
    files = {
        "source": bool(meta.get("has_source")),
        "result": bool(meta.get("has_result")),
    }
    return {
        "id": trial_id,
        "filename": meta.get("filename") or "",
        "created_at": meta.get("created_at") or "",
        "expires_at": meta.get("expires_at") or "",
        "language": meta.get("language") or "vi",
        "mode": meta.get("mode") or "local_only",
        "status": meta.get("status") or "error",
        "engine": meta.get("engine") or "local",
        "model": meta.get("model") or "",
        "message": meta.get("message") or "",
        "elapsed_ms": int(meta.get("elapsed_ms") or 0),
        "logs": list(meta.get("logs") or []),
        "detail": meta.get("detail") if isinstance(meta.get("detail"), dict) else {},
        "ocr_lines": list(meta.get("ocr_lines") or [])[:40],
        "files": files,
    }


def list_trials() -> List[Dict[str, Any]]:
    purge_expired_trials()
    rows: List[Dict[str, Any]] = []
    for folder in trials_root().iterdir():
        if not folder.is_dir() or not _TRIAL_ID_RE.match(folder.name):
            continue
        meta = _read_meta(folder)
        if not meta:
            continue
        rows.append(_public_trial(meta))
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return rows


def get_trial(trial_id: str) -> Optional[Dict[str, Any]]:
    purge_expired_trials()
    folder = _trial_folder(trial_id)
    if folder is None or not folder.is_dir():
        return None
    meta = _read_meta(folder)
    if not meta:
        return None
    return _public_trial(meta)


def trial_file_path(trial_id: str, kind: str) -> Optional[Path]:
    purge_expired_trials()
    if kind not in {"source", "result"}:
        return None
    folder = _trial_folder(trial_id)
    if folder is None:
        return None
    path = folder / f"{kind}.jpg"
    if path.is_file():
        return path
    return None


def delete_trial(trial_id: str) -> bool:
    folder = _trial_folder(trial_id)
    if folder is None or not folder.is_dir():
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return True


def _trial_folder(trial_id: str) -> Optional[Path]:
    if not _TRIAL_ID_RE.match(trial_id or ""):
        return None
    folder = trials_root() / trial_id
    try:
        folder.resolve().relative_to(trials_root().resolve())
    except ValueError:
        return None
    return folder


def describe_trial_engine(mode: str, status: str, detail: Optional[Dict[str, Any]], message: str) -> Dict[str, str]:
    """engine: local | gemini | gpt | kept | deleted | error. model là tên hiển thị."""
    info = detail or {}
    if status == "error":
        return {"engine": "error", "model": ""}
    if status == "deleted":
        return {"engine": "deleted", "model": ""}
    image_engine = str(info.get("image_engine") or "")
    if info.get("gemini_image") or image_engine == "gemini":
        model = (getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "") or "gemini").strip()
        return {"engine": "gemini", "model": model}
    if info.get("gpt_image") or image_engine == "gpt":
        model = (getattr(settings, "IMAGE_LOCALIZATION_OPENAI_IMAGE_MODEL", "") or "gpt-image").strip()
        return {"engine": "gpt", "model": model}
    if status == "kept":
        return {"engine": "kept", "model": ""}
    if mode == "api":
        asked = "Gemini"
    elif mode == "openai":
        asked = "GPT Image"
    else:
        asked = "local"
    return {"engine": "local", "model": f"DeepSeek + vẽ local (job {asked})"}


class _LogCapture(logging.Handler):
    def __init__(self, sink: List[str]):
        super().__init__(level=logging.INFO)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = record.getMessage().strip()
        except Exception:
            return
        if text:
            self.sink.append(text[:500])


def _append_stdout(sink: List[str], chunk: str) -> None:
    for line in chunk.splitlines():
        text = line.strip()
        if text:
            sink.append(text[:500])


def run_trial(
    image_bytes: bytes,
    filename: str,
    *,
    language: str = "vi",
    mode: str = "local_only",
    openai_image_model: str = "",
    openai_image_quality: str = "",
    openai_image_size: str = "",
) -> Dict[str, Any]:
    purge_expired_trials()
    if not image_bytes:
        raise ValueError("Ảnh trống")
    if len(image_bytes) > MAX_TRIAL_BYTES:
        raise ValueError("Ảnh lớn hơn 12MB")
    chosen = (mode or "local_only").strip().lower()
    if chosen not in _MODES:
        raise ValueError("Chế độ phải là local_only, api hoặc openai")
    safe_name = Path(filename or "image.jpg").name[:180] or "image.jpg"
    trial_id = uuid.uuid4().hex
    folder = trials_root() / trial_id
    folder.mkdir(parents=True, exist_ok=False)
    source_path = folder / "source.jpg"
    _write_jpeg_copy(source_path, image_bytes)
    logs: List[str] = [f"Nhận ảnh {safe_name} ({len(image_bytes)} byte), chế độ {chosen}."]
    started = time.perf_counter()
    allow_ai = chosen != "local_only"
    gemini_mode = "openai" if chosen == "openai" else "api"
    result_status = "error"
    result_message = ""
    result_detail: Dict[str, Any] = {}
    ocr_lines: List[str] = []
    has_result = False
    handler = _LogCapture(logs)
    tool_logger = logging.getLogger("app.services.image_localization_service")
    tool_logger.addHandler(handler)
    stdout_buf = io.StringIO()
    gemini = None
    try:
        if allow_ai:
            gemini = build_gemini_image_adapter(
                language or "vi",
                gemini_mode,
                openai_image_model=openai_image_model or None,
                openai_image_quality=openai_image_quality or None,
                openai_image_size=openai_image_size or None,
            )
        else:
            gemini = GeminiApiImageAdapter(language or "vi")
        pipeline = LegacyImageLocalizationPipeline(
            language or "vi",
            gemini,
            allows_ai_image_models=allow_ai,
            gemini_mode=gemini_mode,
            dry_run=True,
        )

        def _save_result(_product, payload: bytes, _filename: str) -> str:
            nonlocal has_result
            (folder / "result.jpg").write_bytes(payload)
            has_result = True
            logs.append(f"Đã lưu ảnh kết quả ({len(payload)} byte).")
            return f"trial://{trial_id}/result.jpg"

        pipeline._upload_bytes = _save_result
        product = SimpleNamespace(
            product_id=f"trial-{trial_id[:8]}",
            code=f"trial-{trial_id[:8]}",
            id=0,
            product_info={},
            shop_name_chinese="",
            category_id=None,
            subcategory="",
        )
        with redirect_stdout(stdout_buf):
            outcome = pipeline.process_single_image(
                product,
                f"trial://{trial_id}/source.jpg",
                image_bytes,
                safe_name,
            )
        result_status = outcome.status or "error"
        result_message = outcome.message or ""
        result_detail = outcome.detail if isinstance(outcome.detail, dict) else {}
        ocr_lines = [str(line) for line in (outcome.consult_ocr_texts or []) if str(line).strip()]
    except Exception as exc:
        result_status = "error"
        result_message = str(exc)[:500]
        logs.append(f"Lỗi: {result_message}")
        logger.warning("Cổng thử bản địa hóa lỗi %s: %s", trial_id, exc)
    finally:
        tool_logger.removeHandler(handler)
        _append_stdout(logs, stdout_buf.getvalue())
        if gemini is not None:
            try:
                gemini.close()
            except Exception:
                pass
    logs.append(f"Kết quả: {result_status}. {result_message}".strip())
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    described = describe_trial_engine(chosen, result_status, result_detail, result_message)
    logs.append(f"Engine: {described['engine']}. Model: {described['model'] or '—'}. {elapsed_ms} ms.")
    if len(logs) > 80:
        logs = [logs[0], *logs[-79:]]
    created = _now()
    meta = {
        "id": trial_id,
        "filename": safe_name,
        "created_at": _iso(created),
        "expires_at": _iso(created + TRIAL_TTL),
        "language": language or "vi",
        "mode": chosen,
        "status": result_status,
        "engine": described["engine"],
        "model": described["model"],
        "message": result_message,
        "elapsed_ms": elapsed_ms,
        "logs": logs[-80:],
        "detail": result_detail,
        "ocr_lines": ocr_lines[:40],
        "has_source": True,
        "has_result": has_result,
    }
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return _public_trial(meta)
