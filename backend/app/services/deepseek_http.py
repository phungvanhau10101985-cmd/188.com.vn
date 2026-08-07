"""Gọi DeepSeek Chat Completions — xử lý SSL thiếu CA trên Windows/dev."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests
from requests.exceptions import SSLError

from app.core.config import settings

logger = logging.getLogger(__name__)
_ssl_fallback_warned = False


def deepseek_ssl_verify() -> bool:
    return bool(getattr(settings, "DEEPSEEK_SSL_VERIFY", True))


def _model_is_deepseek_v4(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("deepseek-v4") or m in {"deepseek-chat", "deepseek-reasoner"}


def deepseek_chat_completions(
    payload: Dict[str, Any],
    *,
    timeout: float = 90,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    disable_thinking: Optional[bool] = None,
) -> requests.Response:
    """
    POST /v1/chat/completions.

    DeepSeek V4 mặc định bật thinking — reasoning chiếm hết max_tokens → content rỗng
    (JSON taxonomy/listing fail). Mặc định tắt thinking cho V4 trừ khi payload đã có
    ``thinking`` hoặc ``disable_thinking=False``.

    Nếu verify SSL fail (thường Windows thiếu CA) → retry verify=False một lần
    trừ khi DEEPSEEK_SSL_VERIFY=false sẵn.
    """
    global _ssl_fallback_warned
    key = (api_key if api_key is not None else getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("Thiếu DEEPSEEK_API_KEY.")
    url = (
        (api_url if api_url is not None else getattr(settings, "DEEPSEEK_API_URL", "") or "")
        .strip()
        or "https://api.deepseek.com/v1/chat/completions"
    )
    body = dict(payload or {})
    model = str(body.get("model") or getattr(settings, "DEEPSEEK_MODEL", "") or "").strip()
    # V4: tắt thinking mặc định để content không bị rỗng khi max_tokens nhỏ / prompt dài.
    if "thinking" not in body:
        want_disable = disable_thinking
        if want_disable is None:
            want_disable = _model_is_deepseek_v4(model)
        if want_disable:
            body["thinking"] = {"type": "disabled"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    verify = deepseek_ssl_verify()
    try:
        return requests.post(url, headers=headers, json=body, timeout=timeout, verify=verify)
    except SSLError:
        if not verify:
            raise
        if not _ssl_fallback_warned:
            logger.warning(
                "DeepSeek SSL verify failed — retry verify=False (dev Windows thiếu CA). "
                "Đặt DEEPSEEK_SSL_VERIFY=false trong backend/.env để bỏ cảnh báo."
            )
            _ssl_fallback_warned = True
            try:
                import urllib3

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        return requests.post(url, headers=headers, json=body, timeout=timeout, verify=False)


def deepseek_message_text(resp_or_body: Any) -> str:
    """Lấy text trả lời từ response DeepSeek (content; fallback reasoning nếu content rỗng)."""
    body: Dict[str, Any]
    if hasattr(resp_or_body, "json") and callable(getattr(resp_or_body, "json")):
        try:
            body = resp_or_body.json()
        except Exception:
            return ""
    elif isinstance(resp_or_body, dict):
        body = resp_or_body
    else:
        return ""
    try:
        msg = ((body.get("choices") or [{}])[0].get("message") or {})
    except Exception:
        return ""
    content = str(msg.get("content") or "").strip()
    if content:
        return content
    # Thinking hết budget → đôi khi chỉ còn reasoning_content
    return str(msg.get("reasoning_content") or "").strip()
