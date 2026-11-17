"""Cache tìm kiếm và TTL RAM không giữ dữ liệu đã hết hạn / JSON cả bảng."""

import json
import time

from app.crud.product_search_cache import (
    SEARCH_LIST_EAGER_FETCH_MAX,
    clear_legacy_paginated_cache_rows,
    clip_search_cache_window,
    get_cached_result,
    legacy_paginated_cache_keys,
    refresh_all_caches,
)
from app.models.product_search_cache import ProductSearchCache
from app.utils.ttl_cache import TTLCache


def test_ttl_cache_drops_expired_on_read_and_keeps_fresh():
    cache = TTLCache()
    now = time.time()
    cache._store["dead"] = (now - 10, 5, "old")
    cache._store["live"] = (now, 60, "ok")

    assert cache.get("dead", 5) is None
    assert "dead" not in cache._store
    assert cache.get("live", 60) == "ok"
    assert "live" in cache._store


def test_ttl_cache_sweeps_unread_expired_keys_only():
    cache = TTLCache()
    now = time.time()
    cache._store["gone"] = (now - 100, 30, {"blob": "x" * 1000})
    cache._store["stay"] = (now, 600, {"ok": 1})
    cache._fetch_locks["gone"] = __import__("threading").Lock()
    cache._last_sweep = 0

    assert cache.get("stay", 600) == {"ok": 1}
    assert "gone" not in cache._store
    assert "gone" not in cache._fetch_locks
    assert cache.get("stay", 600) == {"ok": 1}


def test_clip_search_cache_window_keeps_first_page_window_and_total():
    data = {
        "products": [{"id": index} for index in range(150)],
        "total": 5000,
        "page": 1,
        "size": 48,
    }
    clipped, changed = clip_search_cache_window(data)
    assert changed is True
    assert len(clipped["products"]) == SEARCH_LIST_EAGER_FETCH_MAX
    assert clipped["products"][0]["id"] == 0
    assert clipped["products"][-1]["id"] == SEARCH_LIST_EAGER_FETCH_MAX - 1
    assert clipped["total"] == 5000
    assert len(data["products"]) == 150


def test_clip_search_cache_window_leaves_short_list():
    data = {"products": [{"id": 1}, {"id": 2}], "total": 2}
    clipped, changed = clip_search_cache_window(data)
    assert changed is False
    assert clipped is data


def test_legacy_keys_ignore_rows_without_query_json():
    legacy = json.dumps({"q": "ao", "sk": 48, "li": 48, "pv": 18})
    current = json.dumps({"q": "ao", "sk": 0, "li": 0, "pv": 18})
    keys = legacy_paginated_cache_keys(
        [("old", legacy), ("blank", ""), ("now", current), ("bad", "{")]
    )
    assert keys == ["old"]


def test_clear_legacy_reads_query_json_not_response_body():
    queried: list[tuple[str, ...]] = []
    deleted: list[list[str]] = []

    class Query:
        def __init__(self, names: tuple[str, ...]):
            self.names = names

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def limit(self, *_args, **_kwargs):
            return self

        def all(self):
            if self.names == ("cache_key", "cache_query_json") and queried.count(self.names) == 1:
                return [("old", json.dumps({"sk": 48, "li": 48}))]
            return []

        def delete(self, synchronize_session=False):
            assert synchronize_session is False
            deleted.append(self.names)
            return 1

    class DB:
        def query(self, *cols):
            names = tuple(getattr(col, "key", str(col)) for col in cols)
            queried.append(names)
            return Query(names)

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("không rollback khi xóa thành công")

    deleted_count = clear_legacy_paginated_cache_rows(DB())
    assert deleted_count == 1
    assert queried[0] == ("cache_key", "cache_query_json")
    assert all("response_json" not in names for names in queried)


def test_refresh_all_lists_keys_then_loads_one_row(monkeypatch):
    queried: list[tuple[str, ...]] = []
    full_reads = {"count": 0}

    class KeyQuery:
        def order_by(self, *_args, **_kwargs):
            return self

        def all(self):
            return [("k1",)]

    class RowQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            full_reads["count"] += 1
            return None

    class DB:
        def query(self, *cols):
            names = tuple(getattr(col, "key", "entity") for col in cols)
            queried.append(names)
            if names == ("cache_key",):
                return KeyQuery()
            return RowQuery()

        def expunge(self, _row):
            return None

    monkeypatch.setattr(
        "app.crud.product_search_cache._query_payload_for_row",
        lambda _row: None,
    )
    assert refresh_all_caches(DB()) == 0
    assert queried[0] == ("cache_key",)
    assert full_reads["count"] == 1
    assert ProductSearchCache.response_json.key == "response_json"


def test_get_cached_result_clips_fat_row_without_using_request_commit(monkeypatch):
    fat = {
        "products": [{"id": index} for index in range(130)],
        "total": 900,
        "size": 48,
    }
    persisted: dict = {}

    class Row:
        response_json = json.dumps(fat)

    class Query:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return Row()

    class DB:
        def query(self, *_cols):
            return Query()

        def expire(self, _row):
            self.expired = True

        def commit(self):
            raise AssertionError("không commit session request khi cắt cache")

    monkeypatch.setattr("app.core.redis_cache.is_enabled", lambda: False)

    def _persist(cache_key, data):
        persisted["key"] = cache_key
        persisted["count"] = len(data["products"])
        persisted["total"] = data["total"]

    monkeypatch.setattr(
        "app.crud.product_search_cache._persist_clipped_search_cache",
        _persist,
    )

    page = get_cached_result(DB(), "fat-key")
    assert page is not None
    assert len(page["products"]) == SEARCH_LIST_EAGER_FETCH_MAX
    assert page["products"][0]["id"] == 0
    assert page["total"] == 900
    assert persisted == {"key": "fat-key", "count": SEARCH_LIST_EAGER_FETCH_MAX, "total": 900}
