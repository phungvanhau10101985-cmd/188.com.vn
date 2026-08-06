# backend/tests/test_ladipage_on_view_worker.py
from unittest.mock import MagicMock, patch

from app.services import ladipage_on_view_worker as worker


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
