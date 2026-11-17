"""
TTL cache trong process (singleflight) — dùng cho các endpoint công khai gọi rất nhiều
nhưng dữ liệu hiếm thay đổi (cây danh mục từ sản phẩm, mã nhúng public…).

Mục tiêu: tránh mỗi request SSR Next.js đều mở DB session → pool đầy / QueuePool TimeoutError.

Đặc điểm:
  - get_or_fetch(key, ttl_seconds, fetcher): trả cache nếu còn hạn; nếu hết hạn,
    chỉ MỘT thread chạy fetcher (singleflight) — các request khác chờ giá trị mới.
  - invalidate(key) / invalidate_all(): chủ động xoá khi admin cập nhật.
  - Key đã hết hạn bị xóa khỏi RAM. Key còn hạn giữ nguyên đến hết TTL của lần ghi.

Lưu ý: sống trong RAM của 1 process. Nhiều worker (pm2 cluster) → mỗi worker có cache riêng.
PM2 fork mode (mặc định project này) chỉ 1 process → đủ tốt.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


# Khoảng quét key không còn ai đọc. Key còn hạn không bị quét.
_SWEEP_INTERVAL_SECONDS = 30.0


class TTLCache:
    def __init__(self) -> None:
        self._store_lock = threading.Lock()
        # key → (ghi lúc, ttl lúc ghi hoặc None, giá trị)
        self._store: Dict[str, Tuple[float, Optional[float], Any]] = {}
        self._fetch_locks: Dict[str, threading.Lock] = {}
        self._last_sweep = 0.0

    def _drop_idle_fetch_lock(self, key: str) -> None:
        lock = self._fetch_locks.get(key)
        if lock is not None and not lock.locked():
            self._fetch_locks.pop(key, None)

    def _remember(self, key: str, value: Any, ttl_seconds: Optional[float], now: float) -> None:
        stored_ttl = None if ttl_seconds is None else float(ttl_seconds)
        self._store[key] = (now, stored_ttl, value)
        self._sweep_expired(now)

    def _sweep_expired(self, now: float) -> None:
        if (now - self._last_sweep) < _SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        stale = [
            key
            for key, (ts, ttl, _value) in self._store.items()
            if ttl is not None and (now - ts) > ttl
        ]
        for key in stale:
            self._store.pop(key, None)
            self._drop_idle_fetch_lock(key)

    def _get_fresh(self, key: str, ttl_seconds: float) -> Optional[Any]:
        row = self._store.get(key)
        if not row:
            return None
        ts, _stored_ttl, value = row
        now = time.time()
        if (now - ts) > ttl_seconds:
            self._store.pop(key, None)
            self._drop_idle_fetch_lock(key)
            return None
        return value

    def get(self, key: str, ttl_seconds: float) -> Optional[Any]:
        with self._store_lock:
            self._sweep_expired(time.time())
            return self._get_fresh(key, ttl_seconds)

    def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        with self._store_lock:
            self._remember(key, value, ttl_seconds, time.time())

    def get_or_fetch(
        self,
        key: str,
        ttl_seconds: float,
        fetcher: Callable[[], Any],
    ) -> Any:
        with self._store_lock:
            self._sweep_expired(time.time())
            value = self._get_fresh(key, ttl_seconds)
            if value is not None:
                return value
            fetch_lock = self._fetch_locks.setdefault(key, threading.Lock())

        # Chỉ một thread fetch tại một thời điểm cho mỗi key (singleflight).
        with fetch_lock:
            with self._store_lock:
                value = self._get_fresh(key, ttl_seconds)
                if value is not None:
                    return value

            value = fetcher()

            with self._store_lock:
                self._remember(key, value, ttl_seconds, time.time())
            return value

    def invalidate(self, key: str) -> None:
        with self._store_lock:
            self._store.pop(key, None)
            self._drop_idle_fetch_lock(key)

    def invalidate_all(self) -> None:
        with self._store_lock:
            self._store.clear()
            idle = [key for key, lock in self._fetch_locks.items() if not lock.locked()]
            for key in idle:
                self._fetch_locks.pop(key, None)


cache = TTLCache()
