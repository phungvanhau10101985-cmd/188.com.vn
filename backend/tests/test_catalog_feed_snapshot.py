"""Feed catalog trả file. Client tải chậm không mở transaction Postgres."""

import os
import time

from app.crud.product_search_cache import list_cache_fetch_limit
from app.services.catalog_feed_snapshot import ensure_catalog_feed_file
from app.services.storefront_listing_cache import should_use_listing_filter_cache


def test_fresh_snapshot_does_not_rebuild(tmp_path):
    path = tmp_path / "google-merchant.tsv"
    path.write_text("id\n1\n", encoding="utf-8")
    called = []

    def produce(_db):
        called.append(1)
        return iter(["nope"])

    out = ensure_catalog_feed_file(
        "google-merchant",
        produce,
        max_age_seconds=900,
        directory=tmp_path,
    )
    assert out == path
    assert called == []
    assert out.read_text(encoding="utf-8") == "id\n1\n"


def test_stale_snapshot_is_served_while_refresh_is_scheduled(tmp_path, monkeypatch):
    path = tmp_path / "google-merchant.tsv"
    path.write_text("old\n", encoding="utf-8")
    old = time.time() - 5000
    os.utime(path, (old, old))
    scheduled = []

    def _schedule(name, produce, dest, max_age_seconds):
        scheduled.append(name)

    monkeypatch.setattr("app.services.catalog_feed_snapshot._schedule", _schedule)
    out = ensure_catalog_feed_file(
        "google-merchant",
        lambda _db: iter(["new"]),
        max_age_seconds=30,
        directory=tmp_path,
    )
    assert out.read_text(encoding="utf-8") == "old\n"
    assert scheduled == ["google-merchant"]


def test_missing_snapshot_is_built_before_return(tmp_path, monkeypatch):
    def _build(name, produce, path):
        path.write_text("header\n", encoding="utf-8")

    monkeypatch.setattr("app.services.catalog_feed_snapshot._build", _build)
    out = ensure_catalog_feed_file(
        "meta-catalog",
        lambda _db: iter(["header"]),
        max_age_seconds=30,
        directory=tmp_path,
    )
    assert out.name == "meta-catalog.tsv"
    assert out.read_text(encoding="utf-8") == "header\n"


def test_search_page_does_not_load_thousands_of_rows():
    assert list_cache_fetch_limit(0, 48) == 48
    assert list_cache_fetch_limit(4000, 48) == 120


def test_home_list_uses_listing_cache():
    assert should_use_listing_filter_cache(
        admin_list=False,
        raw_q="",
        pid="",
        order_random=False,
        warehouse_clearance_only=False,
        skip_total=True,
        skip=0,
        limit=8,
    )
    assert not should_use_listing_filter_cache(
        admin_list=False,
        raw_q="áo",
        pid="",
        order_random=False,
        warehouse_clearance_only=False,
        skip_total=True,
        skip=0,
        limit=8,
    )
