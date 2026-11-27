"""Gemini REST: API key đi header, không đi query string (access log / exception URL)."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from requests.exceptions import SSLError, Timeout

GEMINI_API_KEY_HEADER = "x-goog-api-key"
_GEMINI_HOST = "generativelanguage.googleapis.com"
_installed = False


def gemini_auth_headers(
    api_key: str,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if extra:
        for key, value in extra.items():
            headers[str(key)] = str(value)
    token = (api_key or "").strip()
    if token:
        headers[GEMINI_API_KEY_HEADER] = token
    return headers


def relocate_gemini_api_key(url: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Chuyển ?key= / params['key'] của Gemini sang header x-goog-api-key."""
    raw = str(url or "")
    if _GEMINI_HOST not in raw.lower():
        return raw, kwargs

    key = ""
    params = kwargs.get("params")
    if isinstance(params, dict) and params.get("key"):
        key = str(params.get("key") or "").strip()
        kept_params = {name: value for name, value in params.items() if name != "key"}
        if kept_params:
            kwargs["params"] = kept_params
        else:
            kwargs.pop("params", None)

    parts = urlsplit(raw)
    kept_query: list[tuple[str, str]] = []
    for name, value in parse_qsl(parts.query, keep_blank_values=True):
        if name == "key" and value:
            if not key:
                key = value.strip()
            continue
        kept_query.append((name, value))
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept_query), parts.fragment))
    if key:
        headers = dict(kwargs.get("headers") or {})
        headers.setdefault(GEMINI_API_KEY_HEADER, key)
        kwargs["headers"] = headers
    return clean, kwargs


def _ai_label(url: str) -> str:
    raw = str(url or "").lower()
    if "generativelanguage.googleapis.com" in raw:
        marker = "models/"
        if marker in raw:
            name = raw.split(marker, 1)[1].split(":", 1)[0].split("/", 1)[0]
            if name:
                return name
        return "Gemini"
    if "api.openai.com" in raw:
        return "OpenAI"
    if "api.deepseek.com" in raw:
        return "DeepSeek"
    return ""


def _notify_gemini_down(url: str, detail: str) -> None:
    try:
        from app.services.ai_run_alert import notify_ai_down

        notify_ai_down(_ai_label(url) or "Gemini", detail)
    except Exception:
        pass


def install_gemini_key_header_transport() -> None:
    """Lưới an toàn: mọi requests.post tới Gemini đều bị gỡ key khỏi URL trước khi gửi."""
    global _installed
    if _installed:
        return
    original = requests.sessions.Session.request

    def wrapped(self, method, url, **kwargs):
        try:
            url, kwargs = relocate_gemini_api_key(url, kwargs)
        except Exception:
            pass
        label = _ai_label(url)
        verb = str(method or "GET").upper()
        writing = verb not in {"GET", "HEAD"}
        if label and writing:
            from app.services.ai_run_alert import AiApiStopped, ai_is_paused

            if ai_is_paused(label):
                raise AiApiStopped(f"AI_API_STOPPED {label}: đang dừng vì lần gọi trước không chạy")
        try:
            response = original(self, method, url, **kwargs)
        except Exception as exc:
            if label and not isinstance(exc, (SSLError, Timeout)):
                from app.services.ai_run_alert import AiApiStopped

                if isinstance(exc, AiApiStopped):
                    raise
                _notify_gemini_down(url, str(exc))
                raise AiApiStopped(f"AI_API_STOPPED {label}: {exc}") from exc
            raise
        if label:
            code = int(getattr(response, "status_code", 0) or 0)
            if code in (401, 402, 403, 429) or code >= 500:
                body = ""
                try:
                    body = (response.text or "")[:300]
                except Exception:
                    body = ""
                detail = f"HTTP {code} {body}"
                _notify_gemini_down(url, detail)
                from app.services.ai_run_alert import AiApiStopped

                raise AiApiStopped(f"AI_API_STOPPED {label}: {detail}")
            if writing and code < 400:
                try:
                    from app.services.ai_run_alert import mark_ai_ok

                    mark_ai_ok(label)
                except Exception:
                    pass
        return response

    requests.sessions.Session.request = wrapped  # type: ignore[method-assign]
    _installed = True


install_gemini_key_header_transport()
