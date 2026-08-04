"""
Redis cache mỏng — dùng để giảm tải Postgres cho các truy vấn nóng (PDP, listing).

Nguyên tắc an toàn:
- Nếu Redis chưa cài / không kết nối được / lỗi bất kỳ → im lặng bỏ qua cache,
  KHÔNG được để lỗi Redis làm sập request (luôn fallback về DB).
- Timeout socket rất ngắn (mặc định 0.3s) để tránh Redis chậm làm chậm cả request.
- Chỉ bật khi REDIS_ENABLED=true trong env — mặc định tắt để không ảnh hưởng
  VPS chưa cài Redis.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None
_client_init_attempted = False
_client_init_failed = False

# Namespace/version — tăng khi đổi shape payload cache để tự invalidate toàn bộ.
CACHE_VERSION = 1
PDP_CACHE_PREFIX = f"v{CACHE_VERSION}:pdp"
LISTING_CACHE_PREFIX = f"v{CACHE_VERSION}:listing"
MENU_CACHE_PREFIX = f"v{CACHE_VERSION}:menu"
FACET_CACHE_PREFIX = f"v{CACHE_VERSION}:facet"


def _settings():
    from app.core.config import settings

    return settings


def is_enabled() -> bool:
    try:
        return bool(getattr(_settings(), "REDIS_ENABLED", False))
    except Exception:
        return False


def get_client():
    """Trả về client Redis (lazy-init, cache lại instance). None nếu tắt/lỗi."""
    global _client, _client_init_attempted, _client_init_failed

    if not is_enabled():
        return None
    if _client is not None:
        return _client
    if _client_init_attempted and _client_init_failed:
        return None

    _client_init_attempted = True
    try:
        import redis  # type: ignore

        s = _settings()
        timeout = float(getattr(s, "REDIS_SOCKET_TIMEOUT_SECONDS", 0.3))
        _client = redis.Redis.from_url(
            s.REDIS_URL,
            socket_timeout=timeout,
            socket_connect_timeout=timeout,
            health_check_interval=30,
            decode_responses=True,
        )
        # Ping một lần để phát hiện sớm — nếu lỗi, tắt hẳn cho tới lần restart process.
        _client.ping()
        return _client
    except Exception as exc:
        _client_init_failed = True
        _client = None
        logger.warning("redis_cache: không kết nối được Redis (%s) — bỏ qua cache, dùng DB trực tiếp.", exc)
        return None


def get_json(key: str) -> Optional[Any]:
    client = get_client()
    if client is None:
        return None
    try:
        raw = client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("redis_cache.get_json failed key=%s (%s)", key, exc)
        return None


def set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    client = get_client()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value, ensure_ascii=False, default=str), ex=max(1, int(ttl_seconds)))
    except Exception as exc:
        logger.debug("redis_cache.set_json failed key=%s (%s)", key, exc)


def delete(*keys: str) -> None:
    client = get_client()
    if client is None:
        return
    real_keys = [k for k in keys if k]
    if not real_keys:
        return
    try:
        client.delete(*real_keys)
    except Exception as exc:
        logger.debug("redis_cache.delete failed keys=%s (%s)", real_keys, exc)


def pdp_cache_key(slug: str) -> str:
    return f"{PDP_CACHE_PREFIX}:{(slug or '').strip().lower()}"


def invalidate_pdp_cache(*slugs: Optional[str]) -> None:
    """Gọi khi sản phẩm được tạo/sửa/xóa — xóa cache PDP theo slug liên quan."""
    keys = [pdp_cache_key(s) for s in slugs if s]
    delete(*keys)


def listing_cache_key(cache_key: str) -> str:
    return f"{LISTING_CACHE_PREFIX}:{cache_key}"


def menu_cache_key(cache_key: str) -> str:
    return f"{MENU_CACHE_PREFIX}:{cache_key}"


def facet_cache_key(scope_type: str, scope_key: str) -> str:
    return f"{FACET_CACHE_PREFIX}:{scope_type}:{scope_key}"
