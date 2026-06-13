# Proxy NanoAI partner image/text search (Bearer chỉ trên server).
from __future__ import annotations

import logging
import re
from typing import Any, Optional, Tuple

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_IMAGE = 90
DEFAULT_TIMEOUT_TEXT = 60

_HTML_ERROR_SNIPPET_RE = re.compile(
    r"<!doctype\s+html|<html[\s>]|cloudflare|cf-browser-verification|"
    r"attention required|error code 502|error code 503|error code 403",
    re.I,
)


def _looks_like_html_error_page(text: str) -> bool:
    sample = (text or "").strip()[:4000]
    if not sample:
        return False
    return bool(_HTML_ERROR_SNIPPET_RE.search(sample))


def _nanoai_html_error_message(http_status: int) -> str:
    _ = http_status
    return (
        "Dịch vụ nhận diện ảnh NanoAI tạm thời không phản hồi "
        "(máy chủ trả trang lỗi thay vì dữ liệu). "
        "Vui lòng thử lại sau vài phút, thử ảnh khác hoặc dùng Tìm theo chữ."
    )


def _parse_nanoai_http_response(r: requests.Response, *, kind: str) -> Tuple[int, Any]:
    """Parse JSON; nếu NanoAI/Cloudflare trả HTML → thông báo thân thiện, không leak HTML."""
    text = r.text or ""
    ct = (r.headers.get("content-type") or "").lower()
    if "json" in ct or text.lstrip().startswith(("{", "[")):
        try:
            return r.status_code, r.json()
        except Exception:
            logger.warning("NanoAI %s: JSON parse failed status=%s", kind, r.status_code)
    if _looks_like_html_error_page(text):
        logger.warning(
            "NanoAI %s: HTML error page status=%s snippet=%s",
            kind,
            r.status_code,
            text[:160].replace("\n", " "),
        )
        return 502, {
            "ok": False,
            "products": [],
            "error": _nanoai_html_error_message(r.status_code),
        }
    snippet = text.strip().replace("\n", " ")[:280]
    return r.status_code, {
        "ok": False,
        "products": [],
        "error": snippet or "NanoAI trả về dữ liệu không hợp lệ.",
    }


def extract_nanoai_error(body: Any) -> str:
    if isinstance(body, dict):
        for key in ("error", "detail", "message"):
            val = body.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                val = ", ".join(str(x) for x in val if x is not None)
            text = str(val).strip()
            if text:
                if _looks_like_html_error_page(text):
                    return _nanoai_html_error_message(502)
                return text[:500]
    if isinstance(body, str) and body.strip():
        if _looks_like_html_error_page(body):
            return _nanoai_html_error_message(502)
        return body.strip()[:500]
    return "NanoAI tạm thời không phản hồi."


def is_configured() -> bool:
    return bool(
        (getattr(settings, "NANOAI_PARTNER_ID", "") or "").strip()
        and (getattr(settings, "NANOAI_BEARER_TOKEN", "") or "").strip()
    )


def post_image_search(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str],
    limit: int,
) -> Tuple[int, Any]:
    base = (settings.NANOAI_API_BASE or "https://nanoai.vn").rstrip("/")
    partner = settings.NANOAI_PARTNER_ID.strip()
    token = settings.NANOAI_BEARER_TOKEN.strip()
    url = f"{base}/api/messaging/partners/{partner}/image-search"
    headers = {"Authorization": f"Bearer {token}"}
    ct = content_type or "application/octet-stream"
    files = {"image": (filename or "upload.jpg", file_bytes, ct)}
    data = {"limit": str(limit)}
    try:
        r = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=DEFAULT_TIMEOUT_IMAGE,
        )
    except requests.RequestException as e:
        logger.exception("NanoAI image-search request failed: %s", e)
        return 502, {"ok": False, "products": [], "error": "Không kết nối được NanoAI"}
    return _parse_nanoai_http_response(r, kind="image-search")


def post_text_search(query: str, limit: int) -> Tuple[int, Any]:
    base = (settings.NANOAI_API_BASE or "https://nanoai.vn").rstrip("/")
    partner = settings.NANOAI_PARTNER_ID.strip()
    token = settings.NANOAI_BEARER_TOKEN.strip()
    url = f"{base}/api/messaging/partners/{partner}/text-search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(
            url,
            headers=headers,
            json={"q": query, "limit": limit},
            timeout=DEFAULT_TIMEOUT_TEXT,
        )
    except requests.RequestException as e:
        logger.exception("NanoAI text-search request failed: %s", e)
        return 502, {"ok": False, "products": [], "error": "Không kết nối được NanoAI"}
    return _parse_nanoai_http_response(r, kind="text-search")
