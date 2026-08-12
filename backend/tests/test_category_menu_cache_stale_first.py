"""Stale-first menu cache: request path không sync rebuild/prune."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.crud import product as product_crud


def test_build_menu_tree_session_returns_stale_without_sync_rebuild():
    cached = [{"name": "Áo", "slug": "ao", "children": []}]
    db = MagicMock()

    with (
        patch("app.db.session.SessionLocal", return_value=db),
        patch("app.crud.category_menu_cache.read_cached_tree", return_value=cached) as read_mock,
        patch("app.crud.category_menu_cache.schedule_rebuild_both_trees") as sched_mock,
        patch("app.crud.category_menu_cache.rebuild_tree_in_session") as rebuild_mock,
    ):
        out = product_crud._build_menu_tree_session(True)

    assert out == cached
    read_mock.assert_called_once()
    kwargs = read_mock.call_args.kwargs
    assert kwargs.get("allow_stale") is True
    assert kwargs.get("schedule_if_stale") is True
    rebuild_mock.assert_not_called()
    # rebuild chỉ khi stale — do read_cached_tree (schedule_if_stale) xử lý
    sched_mock.assert_not_called()
    db.close.assert_called_once()


def test_build_menu_tree_session_cold_miss_schedules_background_not_sync():
    db = MagicMock()

    with (
        patch("app.db.session.SessionLocal", return_value=db),
        patch("app.crud.category_menu_cache.read_cached_tree", return_value=None),
        patch("app.crud.category_menu_cache.schedule_rebuild_both_trees") as sched_mock,
        patch("app.crud.category_menu_cache.rebuild_tree_in_session") as rebuild_mock,
    ):
        out = product_crud._build_menu_tree_session(True)

    assert out == []
    sched_mock.assert_called_once()
    rebuild_mock.assert_not_called()
    db.close.assert_called_once()


def test_mark_all_stale_keeps_redis_tree_sets_flag():
    from app.crud import category_menu_cache as menu_cache

    db = MagicMock()
    db.query.return_value.filter.return_value.update.return_value = 2

    with (
        patch.object(menu_cache, "_invalidate_menu_ram_only") as ram_only,
        patch.object(menu_cache, "_set_redis_stale_flag") as stale_flag,
        patch.object(menu_cache, "_invalidate_menu_ram_cache") as wipe_all,
    ):
        n = menu_cache.mark_all_stale(db)

    assert n == 2
    ram_only.assert_called_once()
    stale_flag.assert_called_once_with(True)
    wipe_all.assert_not_called()
