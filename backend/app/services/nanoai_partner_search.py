# Proxy NanoAI partner image/text search (Bearer chỉ trên server).
from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_IMAGE = 90
DEFAULT_TIMEOUT_TEXT = 60


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
    try:
        body = r.json()
    except Exception:
        body = {"error": (r.text or "")[:500] or "Invalid JSON from NanoAI"}
    return r.status_code, body


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
    try:
        body = r.json()
    except Exception:
        body = {"error": (r.text or "")[:500] or "Invalid JSON from NanoAI"}
    return r.status_code, body
