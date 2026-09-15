"""Unit tests — mail nhắc đánh giá đơn đã giao chưa review."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.review_reminder import (
    delivered_in_reminder_window,
    order_has_unreviewed_products,
    run_review_reminder_batch,
)


def test_delivered_in_reminder_window_day_3_and_7():
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    assert delivered_in_reminder_window(
        now - timedelta(days=3), now=now, min_days=3, max_days=7
    )
    assert delivered_in_reminder_window(
        now - timedelta(days=7), now=now, min_days=3, max_days=7
    )
    assert not delivered_in_reminder_window(
        now - timedelta(days=2, hours=23), now=now, min_days=3, max_days=7
    )
    assert not delivered_in_reminder_window(
        now - timedelta(days=7, minutes=1), now=now, min_days=3, max_days=7
    )
    assert not delivered_in_reminder_window(None, now=now)


def test_order_has_unreviewed_products_when_one_left():
    order = SimpleNamespace(
        user_id=9,
        items=[SimpleNamespace(product_id=1), SimpleNamespace(product_id=2)],
    )
    db = MagicMock()
    with patch(
        "app.services.review_reminder.crud_product_review.get_user_reviewed_product_ids",
        return_value={1},
    ):
        assert order_has_unreviewed_products(db, order) is True


def test_order_has_unreviewed_products_when_all_done():
    order = SimpleNamespace(
        user_id=9,
        items=[SimpleNamespace(product_id=1), SimpleNamespace(product_id=2)],
    )
    db = MagicMock()
    with patch(
        "app.services.review_reminder.crud_product_review.get_user_reviewed_product_ids",
        return_value={1, 2},
    ):
        assert order_has_unreviewed_products(db, order) is False


def test_run_review_reminder_batch_sends_once_for_unreviewed():
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    order = SimpleNamespace(
        id=42,
        user_id=9,
        customer_name="Lan",
        customer_email="lan@example.com",
        order_code="ORD42",
        delivered_at=now - timedelta(days=4),
        review_reminder_sent_at=None,
        items=[SimpleNamespace(product_id=11, product_name="Sandal")],
        user=None,
    )
    db = MagicMock()
    query = db.query.return_value
    query.options.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value.all.return_value = [order]

    with patch("app.services.review_reminder._enabled", return_value=True), patch(
        "app.services.review_reminder.order_has_unreviewed_products", return_value=True
    ), patch(
        "app.services.review_reminder.send_order_review_reminder_email", return_value=True
    ) as send_mail:
        result = run_review_reminder_batch(db, now=now, limit=10)

    assert result["sent"] == 1
    assert result["sent_order_ids"] == [42]
    send_mail.assert_called_once()
    assert order.review_reminder_sent_at is not None
    db.commit.assert_called()


def test_run_review_reminder_batch_skips_already_reviewed():
    now = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
    order = SimpleNamespace(
        id=42,
        user_id=9,
        customer_name="Lan",
        customer_email="lan@example.com",
        order_code="ORD42",
        delivered_at=now - timedelta(days=4),
        review_reminder_sent_at=None,
        items=[SimpleNamespace(product_id=11, product_name="Sandal")],
        user=None,
    )
    db = MagicMock()
    query = db.query.return_value
    query.options.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value.all.return_value = [order]

    with patch("app.services.review_reminder._enabled", return_value=True), patch(
        "app.services.review_reminder.order_has_unreviewed_products", return_value=False
    ), patch(
        "app.services.review_reminder.send_order_review_reminder_email"
    ) as send_mail:
        result = run_review_reminder_batch(db, now=now, limit=10)

    assert result["sent"] == 0
    assert result["skipped"] == 1
    send_mail.assert_not_called()
    assert order.review_reminder_sent_at is None
