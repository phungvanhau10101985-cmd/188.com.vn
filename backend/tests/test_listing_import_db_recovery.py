"""Lỗi session SQLAlchemy 8s2b khi cào listing — nhận diện + retry."""

from __future__ import annotations

from app.db.retry import is_transient_db_error, is_transient_db_message
from app.services.listing_import_queue import listing_import_outcome_is_retryable


def test_pending_rollback_message_is_transient():
    msg = (
        "Can't reconnect until invalid transaction is rolled back. "
        "Please rollback() fully before proceeding "
        "(Background on this error at: https://sqlalche.me/e/20/8s2b)"
    )
    assert is_transient_db_message(msg)
    assert is_transient_db_error(RuntimeError(msg))


def test_listing_import_outcome_retryable_for_8s2b():
    out = {
        "ok": False,
        "error": "Can't reconnect until invalid transaction is rolled back.",
        "message": "Import draft thất bại: PendingRollbackError",
        "errors": ["PendingRollbackError: Can't reconnect until invalid transaction is rolled back."],
    }
    assert listing_import_outcome_is_retryable(out) is True


def test_listing_import_outcome_not_retryable_for_product_data():
    out = {
        "ok": False,
        "error": "Không tìm thấy biến thể trên Vipomall.",
        "message": "Không tìm thấy biến thể trên Vipomall.",
        "errors": [],
    }
    assert listing_import_outcome_is_retryable(out) is False


def test_ssl_closed_is_retryable():
    out = {"ok": False, "message": "SSL connection has been closed unexpectedly"}
    assert listing_import_outcome_is_retryable(out) is True


def test_requeue_retryable_db_error_items_once():
    from app.services.listing_import_queue import _requeue_retryable_db_error_items

    q = {
        "items": [
            {
                "id": "a",
                "state": "error",
                "message": "Can't reconnect until invalid transaction is rolled back.",
            },
            {
                "id": "b",
                "state": "error",
                "message": "Không tìm thấy biến thể trên Vipomall.",
            },
            {
                "id": "c",
                "state": "error",
                "message": "PendingRollbackError: invalid transaction",
                "db_retry_count": 1,
            },
            {"id": "d", "state": "done", "message": "OK"},
        ]
    }
    n = _requeue_retryable_db_error_items(q)
    assert n == 1
    by_id = {it["id"]: it for it in q["items"]}
    assert by_id["a"]["state"] == "pending"
    assert by_id["a"]["db_retry_count"] == 1
    assert by_id["b"]["state"] == "error"
    assert by_id["c"]["state"] == "error"
    assert _requeue_retryable_db_error_items(q) == 0
