"""
TTL cache trong process (singleflight) — dùng cho các endpoint công khai gọi rất nhiều
nhưng dữ liệu hiếm thay đổi (cây danh mục từ sản phẩm, mã nhúng public…).

Mục tiêu: tránh mỗi request SSR Next.js đều mở DB session → pool đầy / QueuePool TimeoutError.

Đặc điểm:
  - get_or_fetch(key, ttl_seconds, fetcher): trả cache nếu còn hạn; nếu hết hạn,
    chỉ MỘT thread chạy fetcher (singleflight) — các request khác chờ giá trị mới.
  - invalidate(key) / invalidate_all(): chủ động xoá khi admin cập nhật.

Lưu ý: sống trong RAM của 1 process. Nhiều worker (pm2 cluster) → mỗi worker có cache riêng.
PM2 fork mode (mặc định project này) chỉ 1 process → đủ tốt.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:
    def __init__(self) -> None:
        self._store_lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Any]] = {}
        self._fetch_locks: Dict[str, threading.Lock] = {}

    def _get_fresh(self, key: str, ttl_seconds: float) -> Optional[Any]:
        row = self._store.get(key)
        if not row:
            return None
        ts, value = row
        if (time.time() - ts) > ttl_seconds:
            return None
        return value

    def get_or_fetch(
        self,
        key: str,
        ttl_seconds: float,
        fetcher: Callable[[], Any],
    ) -> Any:
        with self._store_lock:
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
                self._store[key] = (time.time(), value)
            return value

    def invalidate(self, key: str) -> None:
        with self._store_lock:
            self._store.pop(key, None)

    def invalidate_all(self) -> None:
        with self._store_lock:
            self._store.clear()


cache = TTLCache()
