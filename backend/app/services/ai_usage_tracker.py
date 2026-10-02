"""Ghi api_usage_log cho mọi POST Gemini / DeepSeek / OpenAI đi qua requests."""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
from typing import Any, Dict, Optional

import requests

from app.services.ai_token_cost import IMAGE_TOKENS

logger = logging.getLogger(__name__)

_GEMINI_MODEL_RE = re.compile(r"/models/([^/:?]+):generateContent", re.IGNORECASE)
_USAGE_FIELD_RE = re.compile(
    r'"(promptTokenCount|prompt_token_count|candidatesTokenCount|candidates_token_count|totalTokenCount|total_token_count)"\s*:\s*(\d+)'
)
_HOOKED = False
_HOOK_LOCK = threading.Lock()
_QUEUE: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=5000)
_WORKER_STARTED = False
_TABLE_READY = False

FEATURE_RULES = (
    ("category_seo_service.py", "category-seo"),
    ("category_size_guide_gemini.py", "size-guide"),
    ("ai_classifier.py", "product-classify"),
    ("search_query_corrector.py", "search-correct"),
    ("image_localization_service.py", "image-localization"),
    ("text_translator.py", "image-translate"),
    ("gemini_post_checker.py", "image-localization"),
    ("ladipage_ai_service.py", "ladipage"),
    ("marketing_banner.py", "marketing-banner"),
    ("marketing_icon.py", "marketing-icon"),
    ("manual_product_create_service.py", "manual-product"),
    ("import_link_gemini_groups.py", "import-groups"),
    ("import_link_deepseek_groups.py", "import-groups"),
    ("import_link_gemini_image_gender.py", "import-gender"),
    ("import_link_deepseek_taxonomy.py", "import-taxonomy"),
    ("variant_color_translate.py", "variant-color"),
    ("legacy_oos_deepseek_keywords.py", "legacy-oos"),
)


def infer_feature_key() -> str:
    import inspect

    for frame in inspect.stack()[2:20]:
        path = (frame.filename or "").replace("\\", "/")
        if path.endswith("ai_usage_tracker.py"):
            continue
        for needle, key in FEATURE_RULES:
            if path.endswith(needle) or f"/{needle}" in path:
                return key
    return ""


def _normalize_image_size(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip().upper().replace(" ", "")
    if text in IMAGE_TOKENS:
        return text
    match = re.search(r"(\d{3,4})\s*[X×]\s*(\d{3,4})", text)
    if not match:
        return None
    longest = max(int(match.group(1)), int(match.group(2)))
    if longest >= 3000:
        return "4K"
    if longest >= 1500:
        return "2K"
    if longest >= 512:
        return "1K"
    return None


def _gemini_image_size(payload: Dict[str, Any]) -> Optional[str]:
    gen = payload.get("generationConfig") or payload.get("generation_config") or {}
    if not isinstance(gen, dict):
        return None
    img = gen.get("imageConfig") or gen.get("image_config") or {}
    if not isinstance(img, dict):
        return None
    return _normalize_image_size(img.get("imageSize") or img.get("image_size"))


def _prompt_chars(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    total = 0
    contents = payload.get("contents") or []
    if isinstance(contents, dict):
        contents = [contents]
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, dict):
                continue
            parts = content.get("parts") or []
            if isinstance(parts, dict):
                parts = [parts]
            for part in parts:
                if isinstance(part, dict) and part.get("text"):
                    total += len(str(part.get("text")))
    messages = payload.get("messages") or []
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict) and message.get("content"):
                content = message.get("content")
                if isinstance(content, str):
                    total += len(content)
    if payload.get("prompt"):
        total += len(str(payload.get("prompt")))
    return total


def _usage_counts(body: Dict[str, Any], payload: Any, image_size: Optional[str]) -> tuple[int, int, int]:
    meta = body.get("usageMetadata") or body.get("usage_metadata") or body.get("usage") or {}
    if not isinstance(meta, dict):
        meta = {}
    prompt = meta.get("promptTokenCount", meta.get("prompt_token_count", meta.get("prompt_tokens", meta.get("input_tokens"))))
    output = meta.get(
        "candidatesTokenCount",
        meta.get("candidates_token_count", meta.get("completion_tokens", meta.get("output_tokens"))),
    )
    total = meta.get("totalTokenCount", meta.get("total_token_count", meta.get("total_tokens")))
    if prompt is None and output is None and total is None:
        prompt_est = max(0, (_prompt_chars(payload) + 3) // 4)
        output_est = IMAGE_TOKENS.get(image_size or "", 1) if image_size else 1
        return prompt_est, output_est, prompt_est + output_est
    prompt_n = int(prompt or 0)
    output_n = int(output or 0)
    total_n = int(total or (prompt_n + output_n))
    return prompt_n, output_n, max(total_n, prompt_n + output_n)


def _model_from_call(url: str, kwargs: Dict[str, Any]) -> str:
    match = _GEMINI_MODEL_RE.search(url or "")
    if match:
        return match.group(1).strip()
    payload = kwargs.get("json")
    if isinstance(payload, dict) and payload.get("model"):
        return str(payload.get("model")).strip()
    data = kwargs.get("data")
    if isinstance(data, dict) and data.get("model"):
        return str(data.get("model")).strip()
    return ""


def _image_size_from_call(url: str, kwargs: Dict[str, Any]) -> Optional[str]:
    payload = kwargs.get("json")
    if isinstance(payload, dict):
        size = _gemini_image_size(payload)
        if size:
            return size
    data = kwargs.get("data")
    if isinstance(data, dict):
        size = _normalize_image_size(data.get("size") or data.get("image_size"))
        if size:
            return size
    if "/images/" in (url or "").lower():
        return None
    return None


def _provider_feature(url: str) -> str:
    low = (url or "").lower()
    if "generativelanguage.googleapis.com" in low:
        return "gemini"
    if "deepseek" in low:
        return "deepseek"
    if "openai" in low:
        return "openai"
    return "ai-other"


def _is_tracked_url(url: str) -> bool:
    low = (url or "").lower()
    if "generativelanguage.googleapis.com" in low and "generatecontent" in low:
        return True
    if "api.deepseek.com" in low or ("deepseek" in low and "chat/completions" in low):
        return True
    if "api.openai.com" in low and ("/chat/completions" in low or "/images/" in low or "/audio/" in low):
        return True
    try:
        from app.core.config import settings

        for attr in ("DEEPSEEK_API_URL", "OPENAI_API_URL"):
            configured = (getattr(settings, attr, "") or "").strip().lower()
            if configured and low.startswith(configured.split("?")[0]):
                return True
    except Exception:
        pass
    return False


def _usage_body_from_tail(content: bytes) -> Dict[str, Any]:
    """Ảnh Nano Banana trả JSON rất lớn. usageMetadata nằm cuối body, không cần parse cả ảnh."""
    tail = content[-80_000:]
    text = tail.decode("utf-8", errors="ignore")
    found: Dict[str, int] = {}
    for match in _USAGE_FIELD_RE.finditer(text):
        found[match.group(1)] = int(match.group(2))
    if not found:
        return {}
    return {
        "usageMetadata": {
            "promptTokenCount": found.get("promptTokenCount", found.get("prompt_token_count")),
            "candidatesTokenCount": found.get("candidatesTokenCount", found.get("candidates_token_count")),
            "totalTokenCount": found.get("totalTokenCount", found.get("total_token_count")),
        }
    }


def parse_tracked_call(url: str, kwargs: Dict[str, Any], response: Any) -> Optional[Dict[str, Any]]:
    """Trả dict để ghi log, hoặc None nếu không phải lượt AI thành công."""
    if not _is_tracked_url(url):
        return None
    status = getattr(response, "status_code", None)
    if status is None or int(status) < 200 or int(status) >= 300:
        return None
    content = getattr(response, "content", b"") or b""
    body: Dict[str, Any]
    if len(content) > 8_000_000:
        body = _usage_body_from_tail(content)
    else:
        try:
            parsed_body = response.json()
        except Exception:
            parsed_body = None
        body = parsed_body if isinstance(parsed_body, dict) else {}
    model = _model_from_call(url, kwargs) or str(body.get("model") or "").strip()
    if not model:
        return None
    image_size = _image_size_from_call(url, kwargs)
    prompt, output, total = _usage_counts(body, kwargs.get("json") or kwargs.get("data"), image_size)
    if total <= 0:
        return None
    feature = infer_feature_key() or _provider_feature(url)
    return {
        "model": model[:160],
        "feature": feature[:80],
        "prompt_token_count": prompt,
        "candidates_token_count": output,
        "total_token_count": total,
        "image_size": image_size,
    }


def _ensure_table(bind) -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    from app.models.api_usage_log import ApiUsageLog

    ApiUsageLog.__table__.create(bind=bind, checkfirst=True)
    _TABLE_READY = True


def _insert_row(row: Dict[str, Any]) -> None:
    from app.db.session import SessionLocal, engine
    from app.models.api_usage_log import ApiUsageLog

    _ensure_table(engine)
    db = SessionLocal()
    try:
        db.add(ApiUsageLog(**row))
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Không ghi được api_usage_log", exc_info=True)
    finally:
        db.close()


def _worker() -> None:
    while True:
        item = _QUEUE.get()
        try:
            if item:
                _insert_row(item)
        finally:
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    with _HOOK_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker, name="ai-usage-log", daemon=True)
        thread.start()
        _WORKER_STARTED = True


def enqueue_usage(row: Dict[str, Any]) -> None:
    _ensure_worker()
    try:
        _QUEUE.put_nowait(row)
    except queue.Full:
        logger.warning("Hàng đợi api_usage_log đầy — bỏ qua một lượt gọi")


def install_ai_usage_tracking() -> None:
    """Bọc requests.Session.request một lần. An toàn khi gọi lại."""
    global _HOOKED
    if _HOOKED or os.environ.get("AI_USAGE_TRACKING", "1").strip().lower() in {"0", "false", "off", "no"}:
        _HOOKED = True
        return
    with _HOOK_LOCK:
        if _HOOKED:
            return
        original = requests.sessions.Session.request

        def wrapped(self, method, url, **kwargs):
            response = original(self, method, url, **kwargs)
            try:
                if str(method or "").lower() == "post":
                    parsed = parse_tracked_call(str(url or ""), kwargs, response)
                    if parsed:
                        enqueue_usage(parsed)
            except Exception:
                logger.debug("Bỏ qua log AI usage", exc_info=True)
            return response

        requests.sessions.Session.request = wrapped  # type: ignore[method-assign]
        _HOOKED = True
        logger.info("Đã bật ghi api_usage_log cho Gemini / DeepSeek / OpenAI")
