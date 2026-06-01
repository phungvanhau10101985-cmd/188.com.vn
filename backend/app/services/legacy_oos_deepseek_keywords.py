"""
DeepSeek: URL sản phẩm đã xóa / không có trong DB → một dòng từ khóa tìm kiếm (tiết kiệm token).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, Optional, Tuple

import requests

from app.core.config import settings
from app.services.legacy_url_keyword_sanitize import strip_vendor_tokens_from_keywords

logger = logging.getLogger(__name__)

_LEGACY_OOS_KEYWORDS_CACHE: Dict[str, Tuple[float, str]] = {}
_LEGACY_OOS_KEYWORDS_CACHE_TTL_SEC = 3600
_LEGACY_OOS_KEYWORDS_CACHE_MAX = 2000
_LEGACY_OOS_KEYWORDS_CACHE_VER = "v3-no-vendor-slug"
_TIMEOUT_SEC = 30


def _legacy_oos_deepseek_enabled() -> bool:
    if not (settings.DEEPSEEK_API_KEY or "").strip():
        return False
    return bool(getattr(settings, "LEGACY_OOS_DEEPSEEK_ENABLED", True))


def _sanitize_search_query(text: str) -> str:
    q = (text or "").strip()
    if not q:
        return ""
    if q.startswith("```"):
        q = re.sub(r"^```(?:\w+)?\s*", "", q, flags=re.I)
        q = re.sub(r"\s*```$", "", q)
    q = q.strip().strip('"').strip("'")
    q = re.sub(r"^từ\s*khóa\s*:\s*", "", q, flags=re.I)
    q = re.sub(r"^tu\s*khoa\s*:\s*", "", q, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    if len(q) > 120:
        q = q[:120].strip()
    return q


def _finalize_search_query(query: str, legacy_path: str) -> str:
    q = _sanitize_search_query(query)
    if not q:
        return ""
    q = strip_vendor_tokens_from_keywords(q, legacy_path)
    return q.strip()


def deepseek_legacy_oos_search_query(legacy_path: str) -> Optional[str]:
    """
    Gọi DeepSeek với URL legacy; trả về từ khóa tìm kiếm (một chuỗi) hoặc None nếu tắt/lỗi.
    """
    path = (legacy_path or "").strip().strip("/")
    if len(path) < 8 or not _legacy_oos_deepseek_enabled():
        return None

    now = time.time()
    cache_key = f"{_LEGACY_OOS_KEYWORDS_CACHE_VER}:{path}"
    hit = _LEGACY_OOS_KEYWORDS_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _LEGACY_OOS_KEYWORDS_CACHE_TTL_SEC:
        cached = (hit[1] or "").strip()
        return cached if cached else None

    key = (settings.DEEPSEEK_API_KEY or "").strip()
    url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-chat"

    system = (
        "URL sản phẩm thời trang VN đã hết. Trả về DUY NHẤT một dòng từ khóa tìm SP thay thế (4-8 từ, tiếng Việt). "
        "Ưu tiên theo thứ tự: (1) loại SP + giới tính nếu có, (2) mùa/vụ, (3) chất liệu. "
        "KHÔNG gồm: thương hiệu, mã NCC trong slug (jitde, gutdu…), tên shop, mã SP, hang hieu, dep, hot, sale, "
        "gia, van chuyen, san pham moi, phong cach/han quoc marketing, mien phi, moi-ma, g0x, số id cuối URL."
    )
    user = f"https://188.com.vn/{path}"

    query: Optional[str] = None
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.1,
                "max_tokens": 48,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=_TIMEOUT_SEC,
        )
        if resp.ok:
            content = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content") or ""
            query = _finalize_search_query(content.split("\n", 1)[0], path)
        else:
            logger.warning(
                "legacy_oos_deepseek: HTTP %s %s",
                resp.status_code,
                (resp.text or "")[:200],
            )
    except requests.RequestException as exc:
        logger.warning("legacy_oos_deepseek: %s", exc)

    if len(_LEGACY_OOS_KEYWORDS_CACHE) >= _LEGACY_OOS_KEYWORDS_CACHE_MAX:
        _LEGACY_OOS_KEYWORDS_CACHE.clear()
    _LEGACY_OOS_KEYWORDS_CACHE[cache_key] = (now, query or "")

    return query if query else None
