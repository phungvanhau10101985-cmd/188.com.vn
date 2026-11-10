"""Xóa hàng loạt không được nạp response_json của product_search_cache."""

from types import SimpleNamespace

from app.crud.product_search_cache import (
    refresh_caches_for_product_states,
    select_matching_search_cache_keys,
)
from app.models.product_search_cache import ProductSearchCache


def test_select_matching_search_cache_keys_uses_keyword_only():
    state = SimpleNamespace(search_document="ao khoac du nam")
    keys = select_matching_search_cache_keys(
        [("keep", "ao khoac"), ("skip", "vay hoa"), ("", "ao"), ("keep2", "   ")],
        [state],
    )
    assert keys == ["keep"]


def test_refresh_expires_without_loading_response_json(monkeypatch):
    queried: list[tuple[str, ...]] = []
    updates: list[dict] = []

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return [("keep", "ao khoac"), ("skip", "vay hoa")]

        def update(self, values, synchronize_session=False):
            updates.append(values)
            return 1

    class DB:
        def query(self, *cols):
            names = []
            for col in cols:
                names.append(getattr(col, "key", getattr(col, "__name__", str(col))))
            queried.append(tuple(names))
            return Query()

        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("không được rollback khi update thành công")

    monkeypatch.setattr("app.core.redis_cache.is_enabled", lambda: False)

    db = DB()
    state = SimpleNamespace(search_document="ao khoac du nam")
    expired = refresh_caches_for_product_states(db, state)

    assert expired == 1
    assert db.committed is True
    assert updates
    assert ProductSearchCache.expires_at in updates[0]
    assert all("response_json" not in cols for cols in queried)
    assert queried[0] == ("cache_key", "norm_q")
