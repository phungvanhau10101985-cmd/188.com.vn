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

logger = logging.getLogger(__name__)

_LEGACY_OOS_KEYWORDS_CACHE: Dict[str, Tuple[float, str]] = {}
_LEGACY_OOS_KEYWORDS_CACHE_TTL_SEC = 3600
_LEGACY_OOS_KEYWORDS_CACHE_MAX = 2000
_LEGACY_OOS_KEYWORDS_CACHE_VER = "v8-vietnamese-only"
_TIMEOUT_SEC = 8


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
        "URL sản phẩm thời trang VN đã hết. Trả về DUY NHẤT một dòng từ khóa tìm SP (3-7 từ). "
        "BẮT BUỘC: chỉ tiếng Việt có dấu, KHÔNG dùng từ tiếng Anh (boot→giày cao cổ, parka→áo khoác dài, "
        "jean→quần bò, oversize→rộng, sandal→dép quai, sneaker→giày thể thao…). "
        "(1) Loại SP danh mục cấp 1 + giới tính (quần nam, váy nữ, giày nữ…). "
        "(2) Đặc tính rõ trong URL: mùa/vụ, kiểu (kẻ caro, sọc…). Giày dép: có chiều cao/đế/cm → cao gót, đế cao, cổ cao. "
        "Không suy mùa/kiểu không có trong URL. Không chất liệu. "
        "Vd quần nam mùa hè vải bông → quần nam mùa hè. "
        "Vd boot-nu chieu-cao-de → giày cao cổ nữ cao gót. "
        "Vd ao-khoac-phao-nu parka cong-so → áo khoác phao nữ công sở. "
        "KHÔNG: thương hiệu, mã NCC, marketing, màu sắc, mã a188, id cuối URL."
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
            query = _sanitize_search_query(content.split("\n", 1)[0])
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
