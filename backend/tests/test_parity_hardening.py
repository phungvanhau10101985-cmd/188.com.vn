from unittest.mock import MagicMock

from sqlalchemy.exc import IntegrityError

from app.crud import product_review as review_crud
from app.db import migrations as migration_module
from app.models.order import Order, OrderStatus
from app.models.product_review import ProductReview
from app.schemas.notification import NotificationPage
from app.services import order_delivery, order_shipper_notify, sepay
from app.services.fulfillment_transition_contract import (
    FULFILLMENT_TRANSITION_CONTRACT_VERSION,
    transition_is_allowed,
)


def test_fulfillment_contract_is_versioned_and_preserves_shipping_flow():
    assert FULFILLMENT_TRANSITION_CONTRACT_VERSION == "2026-09-21.v1"
    assert transition_is_allowed("shipping", "delivered")
    assert not transition_is_allowed("cancelled", "delivered")


def test_customer_review_model_has_unique_user_product_contract():
    names = {
        constraint.name
        for constraint in ProductReview.__table__.constraints
        if constraint.name
    }
    assert "uq_product_reviews_user_product" in names


def test_review_integrity_error_becomes_domain_duplicate(monkeypatch):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(
        group_rating=88
    )
    db.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))

    try:
        review_crud.create_customer_review(
            db,
            product_id=10,
            user_id=20,
            user_name="Khách",
            star=5,
            content="Tốt",
        )
        assert False, "expected duplicate"
    except review_crud.DuplicateCustomerReviewError:
        pass
    db.rollback.assert_called_once()


def test_sepay_integrity_race_returns_duplicate(monkeypatch):
    db = MagicMock()
    order = MagicMock(id=7)
    monkeypatch.setattr(
        sepay,
        "_finalize_sepay_deposit_success",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            IntegrityError("update", {}, Exception("unique"))
        ),
    )
    monkeypatch.setattr(
        sepay.crud_payment,
        "find_payment_by_sepay_id",
        lambda *_args: MagicMock(id=99),
    )
    assert sepay._apply_sepay_deposit_finalize(
        db, order, 100, "SP-1", "", {}, None
    ) == (True, "duplicate")
    db.rollback.assert_called_once()


def test_delivered_hook_is_idempotent_for_terminal_order():
    db = MagicMock()
    order = Order(
        id=1,
        order_code="DH001",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_address="HN",
        status=OrderStatus.DELIVERED,
    )
    assert (
        order_delivery.mark_order_delivered(
            db, order, source="ems_auto"
        )
        is False
    )


def test_shipper_queue_dedupes_pending_order(monkeypatch):
    queued: list[int] = []
    monkeypatch.setattr(order_shipper_notify, "_ensure_worker", lambda: None)
    monkeypatch.setattr(
        order_shipper_notify._QUEUE, "put", lambda value: queued.append(value)
    )
    with order_shipper_notify._QUEUE_LOCK:
        order_shipper_notify._QUEUED.clear()
    order_shipper_notify.schedule_customer_shipper_confirmed_notify(42)
    order_shipper_notify.schedule_customer_shipper_confirmed_notify(42)
    assert queued == [42]
    with order_shipper_notify._QUEUE_LOCK:
        order_shipper_notify._QUEUED.clear()


def test_notification_page_contract_is_backward_compatible_counterpart():
    page = NotificationPage(items=[], total=25, skip=20, limit=20, has_more=True)
    assert page.has_more is True
    assert page.items == []


def test_startup_hardening_audit_never_mutates_business_rows(monkeypatch):
    statements: list[str] = []

    class Result:
        def scalar(self):
            return 0

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement):
            statements.append(str(statement))
            return Result()

    class Engine:
        def connect(self):
            return Connection()

    class Inspector:
        def get_table_names(self):
            return ["payments", "product_reviews", "notifications"]

        def get_columns(self, _table):
            return [{"name": "dedupe_key"}]

    monkeypatch.setattr(migration_module, "engine", Engine())
    monkeypatch.setattr(migration_module, "inspect", lambda _engine: Inspector())

    assert migration_module.MigrationManager().migrate_hardening_unique_indexes()
    assert statements
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in statements)
