import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from app.api.endpoints import sepay_webhook
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.product import Product
from app.services import checkout_fulfillment, deposit_sla, sepay, warehouse_stock


def _product(*, available: int, reserved: int = 0) -> Product:
    row = Product(
        id=11,
        product_id="VN-11",
        code="VN-11",
        name="Hàng Việt Nam",
        price=Decimal("100000"),
        available=available,
    )
    row.warehouse_reserved = reserved
    return row


def _stock_order(product: Product, *, status: OrderStatus, quantity: int = 2) -> Order:
    item = OrderItem(
        id=21,
        product_id=product.id,
        product=product,
        product_name=product.name,
        unit_price=product.price,
        total_price=product.price * quantity,
        quantity=quantity,
        fulfillment_source="vietnam",
    )
    return Order(
        id=31,
        order_code="DH031",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_address="Hà Nội",
        fulfillment_source="vietnam",
        status=status,
        items=[item],
    )


def test_sellable_is_available_minus_reserved_and_cod_reserves(monkeypatch):
    product = _product(available=7, reserved=3)
    assert warehouse_stock.warehouse_sellable_qty(product) == 4

    order = _stock_order(product, status=OrderStatus.CONFIRMED, quantity=4)
    monkeypatch.setattr(warehouse_stock, "_lock_product", lambda *_args: product)
    warehouse_stock.reserve_warehouse_stock_for_order(MagicMock(), order)

    assert product.available == 7
    assert product.warehouse_reserved == 7
    assert order.items[0].warehouse_stock_reserved_at is not None
    assert order.items[0].warehouse_stock_additive is True


def test_reserve_release_deduct_restore_are_idempotent(monkeypatch):
    product = _product(available=5)
    order = _stock_order(product, status=OrderStatus.CONFIRMED)
    monkeypatch.setattr(warehouse_stock, "_lock_product", lambda *_args: product)
    db = MagicMock()

    warehouse_stock.reserve_warehouse_stock_for_order(db, order)
    warehouse_stock.reserve_warehouse_stock_for_order(db, order)
    assert (product.available, product.warehouse_reserved) == (5, 2)

    warehouse_stock.release_warehouse_stock_for_order(db, order)
    warehouse_stock.release_warehouse_stock_for_order(db, order)
    assert (product.available, product.warehouse_reserved) == (5, 0)

    warehouse_stock.reserve_warehouse_stock_for_order(db, order)
    warehouse_stock.deduct_warehouse_stock_for_order(db, order)
    warehouse_stock.deduct_warehouse_stock_for_order(db, order)
    assert (product.available, product.warehouse_reserved) == (3, 0)

    warehouse_stock.restore_warehouse_stock_for_order(db, order)
    warehouse_stock.restore_warehouse_stock_for_order(db, order)
    assert (product.available, product.warehouse_reserved) == (5, 0)


def test_late_deposit_re_reserves_released_vietnam_stock(monkeypatch):
    product = _product(available=3)
    order = _stock_order(product, status=OrderStatus.DEPOSIT_PAID, quantity=2)
    order.stock_hold_released_at = datetime.now(timezone.utc)
    order.deposit_hold_overdue = True
    order.deposit_exception = True
    order.deposit_exception_note = "old"
    monkeypatch.setattr(warehouse_stock, "_lock_product", lambda *_args: product)

    warehouse_stock.reserve_warehouse_stock_for_order(MagicMock(), order)

    assert product.warehouse_reserved == 2
    assert order.stock_hold_released_at is None
    assert order.deposit_hold_overdue is False
    assert order.deposit_exception is False
    assert order.deposit_exception_note is None


def test_split_checkout_service_rolls_back_on_any_group_failure(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(
        checkout_fulfillment,
        "_create_checkout_fulfillment",
        lambda **_kwargs: (_ for _ in ()).throw(
            warehouse_stock.WarehouseStockError("group two failed")
        ),
    )

    with pytest.raises(warehouse_stock.WarehouseStockError):
        checkout_fulfillment.create_checkout_fulfillment(
            db=db,
            order_data=MagicMock(),
            current_user=None,
            background_tasks=BackgroundTasks(),
        )

    db.rollback.assert_called_once()


def _sla_query_for(order: Order) -> MagicMock:
    query = MagicMock()
    query.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        order
    ]
    return query


def test_china_waiting_deposit_gets_reminders_but_never_release_or_auto_cancel(monkeypatch):
    order = Order(
        id=41,
        order_code="DH041",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_email="customer@example.com",
        customer_address="Hà Nội",
        fulfillment_source="china",
        status=OrderStatus.WAITING_DEPOSIT,
        created_at=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    db = MagicMock()
    db.query.return_value = _sla_query_for(order)
    sent: list[int] = []
    released: list[int] = []
    monkeypatch.setattr(deposit_sla, "_send_reminder", lambda _o, h: sent.append(h) or True)
    monkeypatch.setattr(
        deposit_sla,
        "release_warehouse_stock_for_order",
        lambda _db, row: released.append(row.id),
    )
    monkeypatch.setattr(deposit_sla.settings, "DEPOSIT_REMIND_HOURS", [2, 20])
    monkeypatch.setattr(deposit_sla.settings, "VN_STOCK_HOLD_HOURS", 24)
    monkeypatch.setattr(deposit_sla.settings, "AUTO_CANCEL_EXPIRED_DEPOSIT", True)

    result = deposit_sla.process_deposit_sla(db)

    assert sent == [2, 20]
    assert released == []
    assert result["cancelled"] == 0
    assert getattr(order.status, "value", order.status) == "waiting_deposit"


def test_vietnam_auto_cancel_is_an_explicit_opt_in_policy(monkeypatch):
    order = Order(
        id=42,
        order_code="DH042",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_address="Hà Nội",
        fulfillment_source="vietnam",
        status=OrderStatus.WAITING_DEPOSIT,
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        deposit_reminded_at_2h=datetime.now(timezone.utc),
        deposit_reminded_at_20h=datetime.now(timezone.utc),
        deposit_hold_overdue=False,
    )
    db = MagicMock()
    db.query.return_value = _sla_query_for(order)
    monkeypatch.setattr(deposit_sla, "release_warehouse_stock_for_order", lambda *_args: None)
    monkeypatch.setattr(deposit_sla.settings, "DEPOSIT_REMIND_HOURS", [2, 20])
    monkeypatch.setattr(deposit_sla.settings, "VN_STOCK_HOLD_HOURS", 24)
    monkeypatch.setattr(deposit_sla.settings, "AUTO_CANCEL_EXPIRED_DEPOSIT", True)
    monkeypatch.setattr(
        deposit_sla.affiliate_svc, "handle_order_status_change", lambda *_args: None
    )

    result = deposit_sla.process_deposit_sla(db)

    assert result["stock_released"] == 1
    assert result["cancelled"] == 1
    assert getattr(order.status, "value", order.status) == "cancelled"


def test_sepay_success_without_pending_payment_stays_in_one_transaction(monkeypatch):
    order = Order(
        id=51,
        order_code="DH051",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_address="Hà Nội",
        total_amount=Decimal("300000"),
        deposit_type="percent_30",
        status=OrderStatus.WAITING_DEPOSIT,
        requires_deposit=True,
    )
    db = MagicMock()
    calls: list[dict] = []
    monkeypatch.setattr(
        sepay.crud_payment,
        "create_payment",
        lambda **kwargs: calls.append(kwargs) or MagicMock(),
    )
    monkeypatch.setattr(
        sepay.affiliate_svc, "grant_deposit_commission_for_order", lambda *_args: None
    )
    monkeypatch.setattr(
        "app.services.order_shipment_timeline.ensure_shipment_timeline",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.services.warehouse_stock.reload_order_with_items",
        lambda *_args: order,
    )
    monkeypatch.setattr(
        "app.services.warehouse_stock.reserve_warehouse_stock_for_order",
        lambda *_args: None,
    )

    sepay._finalize_sepay_deposit_success(
        db,
        order,
        Decimal("90000"),
        "SP-ATOMIC-1",
        "REF",
        {"id": "SP-ATOMIC-1"},
        None,
    )

    assert calls[0]["commit"] is False
    db.commit.assert_called_once()
    assert getattr(order.status, "value", order.status) == "deposit_paid"
    assert order.payment_status == PaymentStatus.DEPOSIT_PAID


def test_late_sepay_deposit_without_stock_is_persisted_as_admin_exception(monkeypatch):
    order = Order(
        id=52,
        order_code="DH052",
        customer_name="Khách",
        customer_phone="0900000000",
        customer_address="Hà Nội",
        status=OrderStatus.WAITING_DEPOSIT,
        requires_deposit=True,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = order
    exception_payment = MagicMock()
    created: list[dict] = []
    monkeypatch.setattr(
        sepay,
        "_finalize_sepay_deposit_success",
        lambda *_args: (_ for _ in ()).throw(
            warehouse_stock.WarehouseStockError("chỉ còn 0")
        ),
    )
    monkeypatch.setattr(
        sepay.crud_payment,
        "create_payment",
        lambda **kwargs: created.append(kwargs) or exception_payment,
    )
    monkeypatch.setattr(sepay.settings, "ORDER_DEPOSIT_ALERT_EMAILS", [])

    result = sepay._apply_sepay_deposit_finalize(
        db,
        order,
        Decimal("90000"),
        "SP-LATE-OOS-1",
        "REF",
        {"id": "SP-LATE-OOS-1"},
        None,
    )

    assert result == (False, "warehouse_out_of_stock")
    db.rollback.assert_called_once()
    db.commit.assert_called_once()
    assert order.deposit_exception is True
    assert "tồn kho Việt Nam không đủ" in order.deposit_exception_note
    assert created[0]["payment_type"] == "deposit_sepay_exception"
    assert created[0]["transaction_code"] == "SP-LATE-OOS-1"
    assert created[0]["payment_status"] == PaymentStatus.PENDING.value


def test_sepay_service_uses_persisted_transaction_as_replay_guard(monkeypatch):
    monkeypatch.setattr(
        sepay.crud_payment,
        "find_payment_by_sepay_id",
        lambda _db, transaction_id: MagicMock(id=71)
        if transaction_id == "SP-REPLAY-DB-1"
        else None,
    )

    assert sepay.apply_sepay_incoming_transfer(
        MagicMock(),
        {
            "id": "SP-REPLAY-DB-1",
            "transferType": "in",
            "transferAmount": "90000",
        },
    ) == (True, "duplicate", None)


def test_sepay_db_replay_is_acknowledged_without_external_side_effects(monkeypatch):
    request = MagicMock()
    request.body = AsyncMock(return_value=b'{"id":"SP-REPLAY-1"}')
    request.client = None
    request.headers = {"content-type": "application/json"}
    applied: list[str] = []
    emailed: list[int] = []
    capi: list[int] = []
    monkeypatch.setattr(sepay_webhook.sepay_svc, "verify_webhook", lambda *_args: True)
    monkeypatch.setattr(
        sepay_webhook.sepay_svc,
        "parse_webhook_payload",
        lambda *_args: {"id": "SP-REPLAY-1"},
    )
    monkeypatch.setattr(
        sepay_webhook.sepay_svc,
        "apply_sepay_incoming_transfer",
        lambda *_args: applied.append("db lookup") or (True, "duplicate", None),
    )
    monkeypatch.setattr(
        sepay_webhook, "schedule_deposit_confirmed_email", lambda oid: emailed.append(oid)
    )
    monkeypatch.setattr(
        sepay_webhook, "schedule_meta_purchase_capi_for_order", lambda oid: capi.append(oid)
    )

    response = asyncio.run(
        sepay_webhook._handle_sepay_webhook_post(
            request, BackgroundTasks(), MagicMock()
        )
    )

    assert response.status_code == 201
    assert applied == ["db lookup"]
    assert emailed == []
    assert capi == []
