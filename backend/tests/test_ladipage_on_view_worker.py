# backend/tests/test_ladipage_on_view_worker.py
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.models.product import Product
from app.services import ladipage_on_view_worker as worker
from app.services.admin_source_stock_batch import recent_customer_view_exists


def test_enqueue_disabled_returns_false():
    with patch.object(worker, "ladipage_on_view_enabled", return_value=False):
        assert worker.enqueue_ladipage_on_view_if_needed(42) is False


def test_enqueue_dedupes_same_product():
    worker._queue.clear()
    worker._queued_ids.clear()
    with patch.object(worker, "ladipage_on_view_enabled", return_value=True):
        assert worker.enqueue_ladipage_on_view_if_needed(99) is True
        assert worker.enqueue_ladipage_on_view_if_needed(99) is False
    worker._queue.clear()
    worker._queued_ids.clear()


def test_should_skip_when_inactive_or_has_ladipage():
    db = MagicMock()
    product = MagicMock(is_active=False)
    db.query.return_value.filter.return_value.first.return_value = product
    assert worker._should_skip_product(db, 1) is True

    product.is_active = True
    with patch(
        "app.services.ladipage_on_view_worker.find_single_product_ladipages_for_product",
        return_value=[MagicMock()],
    ):
        assert worker._should_skip_product(db, 1) is True


def test_recent_view_predicate_scans_window_once():
    clause = recent_customer_view_exists(
        Product, datetime(2026, 10, 18, tzinfo=timezone.utc)
    )
    sql = str(clause.compile(compile_kwargs={"literal_binds": True})).upper()
    assert "UNION" in sql
    assert "USER_PRODUCT_VIEWS" in sql
    assert "GUEST_PRODUCT_VIEWS" in sql
    assert "VIEWED_AT" in sql
    assert "EXISTS" not in sql


def test_scan_failure_returns_zero_and_closes_session():
    worker._last_scan_at = None
    db = MagicMock()
    db.execute.side_effect = RuntimeError("ssl closed")
    try:
        with (
            patch.object(worker, "SessionLocal", return_value=db),
            patch.object(worker.settings, "IS_POSTGRESQL", True),
        ):
            assert worker._scan_and_enqueue_backlog(5) == 0
        db.rollback.assert_called()
        db.close.assert_called()
    finally:
        worker._last_scan_at = None
