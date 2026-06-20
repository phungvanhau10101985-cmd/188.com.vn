"""
Rate limit toàn API — Sliding Window Log trong RAM (single VPS).
Bỏ qua SSR nội bộ (peer loopback không có IP client), /health*, /static, OPTIONS.
"""
from __future__ import annotations

import asyncio
import ipaddress
import math
import time
from collections import deque
from typing import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

_EXEMPT_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_CLEANUP_INTERVAL_SEC = 300.0
_WINDOW_SEC = 60.0


def _normalize_ip(raw: str) -> str:
    t = (raw or "").strip()
    if t.lower().startswith("::ffff:"):
        return t[7:]
    if "%" in t:
        t = t.split("%", 1)[0]
    return t


def _peer_trusted(peer_host: str) -> bool:
    if not peer_host:
        return False
    try:
        ip = ipaddress.ip_address(_normalize_ip(peer_host))
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private)


def _header_map(headers: Iterable[tuple[bytes, bytes]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers:
        lk = key.decode("latin-1").lower()
        if lk not in out:
            out[lk] = value.decode("utf-8", errors="ignore")
    return out


def _client_ip_from_scope(scope: Scope) -> str:
    peer = ""
    client = scope.get("client")
    if client and len(client) > 0:
        peer = _normalize_ip(str(client[0] or ""))

    headers = _header_map(scope.get("headers") or [])
    trusted = _peer_trusted(peer)

    if trusted:
        cf = (headers.get("cf-connecting-ip") or "").strip()
        if cf:
            return _normalize_ip(cf)

        xff = (headers.get("x-forwarded-for") or "").strip()
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return _normalize_ip(first)

        real = (headers.get("x-real-ip") or "").strip()
        if real:
            return _normalize_ip(real)

    if peer:
        return peer
    return "unknown"


def _is_internal_exempt(ip: str) -> bool:
    if ip in _EXEMPT_LOOPBACK or ip == "unknown":
        return True
    try:
        return ipaddress.ip_address(_normalize_ip(ip)).is_loopback
    except ValueError:
        return False


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.buckets: dict[str, deque[float]] = {}
        self.lock = asyncio.Lock()
        self.last_cleanup = time.time()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            await self.app(scope, receive, send)
            return

        method = (scope.get("method") or "GET").upper()
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if path.startswith("/health") or path.startswith("/static"):
            await self.app(scope, receive, send)
            return

        ip = _client_ip_from_scope(scope)
        if _is_internal_exempt(ip):
            await self.app(scope, receive, send)
            return

        now = time.time()
        limit = int(getattr(settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 60))

        async with self.lock:
            if now - self.last_cleanup > _CLEANUP_INTERVAL_SEC:
                self._cleanup_stale_buckets(now, _WINDOW_SEC)

            bucket = self.buckets.setdefault(ip, deque())

            while bucket and now - bucket[0] > _WINDOW_SEC:
                bucket.popleft()

            if len(bucket) >= limit:
                oldest = bucket[0]
                retry_after = max(1, int(math.ceil(oldest + _WINDOW_SEC - now)))
                detail = (
                    f"Bạn đang thao tác quá nhanh. Vui lòng thử lại sau {retry_after} giây."
                )
                response = JSONResponse(
                    status_code=429,
                    content={"detail": detail, "retry_after_seconds": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
                await response(scope, receive, send)
                return

            bucket.append(now)

        await self.app(scope, receive, send)

    def _cleanup_stale_buckets(self, now: float, window: float) -> None:
        stale_ips: list[str] = []
        for ip, bucket in self.buckets.items():
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if not bucket:
                stale_ips.append(ip)

        for ip in stale_ips:
            self.buckets.pop(ip, None)

        self.last_cleanup = now
