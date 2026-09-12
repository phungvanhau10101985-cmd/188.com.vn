from decimal import Decimal

from app.services.fulfillment_routing import (
    FULFILLMENT_CHINA,
    FULFILLMENT_VIETNAM,
    fulfillment_source_from_url,
    source_platform_from_url,
    allocate_decimal_total,
    classify_legacy_item_source,
)
from app.services.order_shipment_timeline import _step_defs, _sync_order_processing_status
from app.services.checkout_fulfillment import (
    allocate_group_wallet,
    build_group_financial_plan,
    group_checkout_items,
)
from app.services.order_sla import business_hours_between
from app.services.order_sla import enrich_admin_orders_sla
from app.models.order_shipment import OrderShipmentEvent
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
from app.models.order import Order, OrderStatus
from app.services import deposit_sla
from app.services import warehouse_stock
from app.models.order import OrderItem
from app.models.product import Product
from app.crud.order import admin_update_order
from app.schemas.order import OrderUpdate
import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
import app.models.sale_calendar  # đăng ký bảng pricing dùng trong smoke SQLite
from app.api.endpoints import orders as order_endpoints
from app.schemas.order import OrderCreate, OrderItemCreate
from app.models.order import PaymentMethod


def test_china_source_hosts_and_subdomains():
    assert source_platform_from_url("https://detail.1688.com/offer/1.html") == "1688"
    assert source_platform_from_url("item.taobao.com/item.htm?id=1") == "taobao"
    assert source_platform_from_url("https://detail.tmall.com/item.htm?id=1") == "tmall"
    assert fulfillment_source_from_url("https://www.1688.com/") == FULFILLMENT_CHINA


def test_missing_other_and_spoofed_hosts_are_vietnam():
    assert fulfillment_source_from_url(None) == FULFILLMENT_VIETNAM
    assert fulfillment_source_from_url("") == FULFILLMENT_VIETNAM
    assert fulfillment_source_from_url("https://example.vn/product") == FULFILLMENT_VIETNAM
    assert fulfillment_source_from_url("https://1688.com.evil.test/item") == FULFILLMENT_VIETNAM
    assert fulfillment_source_from_url("https://evil.test/?next=taobao.com") == FULFILLMENT_VIETNAM


def test_legacy_backfill_only_flags_missing_or_mixed_source_data():
    existing_blank = classify_legacy_item_source(
        snapshot_url=None,
        product_url=None,
        product_exists=True,
    )
    missing_product = classify_legacy_item_source(
        snapshot_url=None,
        product_url=None,
        product_exists=False,
        snapshot_source=None,
    )
    china_snapshot = classify_legacy_item_source(
        snapshot_url="https://detail.1688.com/offer/1.html",
        product_url=None,
        product_exists=False,
    )
    assert existing_blank == ("vietnam", None, False)
    assert missing_product == ("vietnam", None, True)
    assert china_snapshot == (
        "china",
        "https://detail.1688.com/offer/1.html",
        False,
    )
    assert len({existing_blank[0], china_snapshot[0]}) == 2


def test_vietnam_timeline_has_no_cross_border_steps():
    keys = [step["key"] for step in _step_defs(False, FULFILLMENT_VIETNAM)]
    assert keys == ["order_confirmed", "vn_picking", "vn_packed", "awaiting_confirm"]
    assert not {"tq_preparing", "international_shipping", "at_customs"} & set(keys)


def test_vietnam_stays_confirmed_until_admin_starts_picking_but_china_auto_processes():
    vietnam = Order(
        id=30,
        order_code="DH030",
        customer_name="VN",
        customer_phone="0900000000",
        customer_address="Ha Noi",
        fulfillment_source="vietnam",
        status=OrderStatus.CONFIRMED,
    )
    china = Order(
        id=31,
        order_code="DH031",
        customer_name="CN",
        customer_phone="0900000001",
        customer_address="Ha Noi",
        fulfillment_source="china",
        status=OrderStatus.CONFIRMED,
    )
    _sync_order_processing_status(
        MagicMock(),
        vietnam,
        [OrderShipmentEvent(step_key="vn_picking", status="active")],
    )
    _sync_order_processing_status(
        MagicMock(),
        china,
        [OrderShipmentEvent(step_key="tq_preparing", status="active")],
    )
    assert getattr(vietnam.status, "value", vietnam.status) == "confirmed"
    assert getattr(china.status, "value", china.status) == "processing"


def test_china_timeline_keeps_existing_steps():
    keys = [step["key"] for step in _step_defs(True, FULFILLMENT_CHINA)]
    assert keys == [
        "deposit_confirmed",
        "tq_preparing",
        "tq_warehouse",
        "international_shipping",
        "at_customs",
        "domestic_shipping",
        "awaiting_confirm",
    ]


def test_money_allocation_preserves_total_and_rounding():
    allocated = allocate_decimal_total(
        Decimal("10000"),
        {"vietnam": Decimal("1"), "china": Decimal("2")},
        ["vietnam", "china"],
    )
    assert allocated == {
        "vietnam": Decimal("3333.33"),
        "china": Decimal("6666.67"),
    }
    assert sum(allocated.values(), Decimal("0")) == Decimal("10000")


def test_grouping_is_stable_vietnam_then_china_and_single_source_stays_single():
    mixed = group_checkout_items(
        [
            {"fulfillment_source": "china", "total_price": Decimal("200")},
            {"fulfillment_source": "vietnam", "total_price": Decimal("100")},
        ]
    )
    assert list(mixed) == ["vietnam", "china"]
    assert len(mixed) == 2
    assert list(
        group_checkout_items(
            [{"fulfillment_source": "china", "total_price": Decimal("200")}]
        )
    ) == ["china"]


def test_wallet_is_allocated_once_by_group_weight_with_rounding_on_last_group():
    allocated = allocate_group_wallet(
        Decimal("100"),
        {"vietnam": Decimal("100"), "china": Decimal("200")},
        ["vietnam", "china"],
    )
    assert allocated == {
        "vietnam": Decimal("33.33"),
        "china": Decimal("66.67"),
    }
    assert sum(allocated.values(), Decimal("0")) == Decimal("100")


def test_four_source_and_deposit_combinations_have_expected_initial_flow():
    for source in ("vietnam", "china"):
        no_deposit = build_group_financial_plan(
            [{"fulfillment_source": source, "total_price": Decimal("400000"), "requires_deposit": False}],
            discount=Decimal("0"),
            shipping_fee=Decimal("30000") if source == "vietnam" else Decimal("0"),
            requested_deposit_type=None,
        )
        assert no_deposit["initial_status"] == "confirmed"
        assert no_deposit["deposit_amount"] == Decimal("0")
        assert no_deposit["remaining_amount"] == no_deposit["total"]
        assert _step_defs(False, source)

        deposit = build_group_financial_plan(
            [{"fulfillment_source": source, "total_price": Decimal("400000"), "requires_deposit": True}],
            discount=Decimal("10000"),
            shipping_fee=Decimal("30000") if source == "vietnam" else Decimal("0"),
            requested_deposit_type=None,
        )
        assert deposit["initial_status"] == "waiting_deposit"
        assert deposit["deposit_amount"] == Decimal("117000.00")
        assert deposit["remaining_amount"] + deposit["deposit_amount"] == deposit["total"]
        assert _step_defs(True, source)


def test_mixed_checkout_money_invariant_and_shipping_only_vietnam():
    group_totals = {"vietnam": Decimal("400000"), "china": Decimal("600000")}
    discounts = allocate_decimal_total(
        Decimal("100000"), group_totals, ["vietnam", "china"]
    )
    wallets = allocate_group_wallet(
        Decimal("90000"),
        {
            source: group_totals[source] - discounts[source]
            for source in ("vietnam", "china")
        },
        ["vietnam", "china"],
    )
    shipping = {"vietnam": Decimal("30000"), "china": Decimal("0")}
    checkout_total = sum(group_totals.values()) - sum(discounts.values()) + sum(shipping.values())
    cod_or_deposit_total = checkout_total - sum(wallets.values())
    assert sum(shipping.values()) == Decimal("30000")
    assert shipping["china"] == Decimal("0")
    assert sum(wallets.values()) + cod_or_deposit_total == checkout_total


def test_business_hours_excludes_sunday_and_outside_8_to_18():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    start = datetime(2026, 9, 12, 17, 0, tzinfo=tz)  # Saturday
    end = datetime(2026, 9, 14, 11, 0, tzinfo=tz)  # Monday
    assert business_hours_between(start, end) == 4


def test_deposit_sla_reminders_and_release_are_idempotent(monkeypatch):
    order = Order(
        id=1,
        order_code="DH001",
        customer_name="Khach",
        customer_phone="0900000000",
        customer_email="customer@example.com",
        customer_address="Ha Noi",
        fulfillment_source="vietnam",
        status=OrderStatus.WAITING_DEPOSIT,
        created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        deposit_hold_overdue=False,
    )
    query = MagicMock()
    query.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [order]
    db = MagicMock()
    db.query.return_value = query
    sent: list[int] = []
    released: list[int] = []
    monkeypatch.setattr(deposit_sla, "_send_reminder", lambda row, hours: sent.append(hours) or True)
    monkeypatch.setattr(
        deposit_sla,
        "release_warehouse_stock_for_order",
        lambda _db, row: released.append(row.id),
    )
    monkeypatch.setattr(deposit_sla.settings, "DEPOSIT_REMIND_HOURS", [2, 20])
    monkeypatch.setattr(deposit_sla.settings, "VN_STOCK_HOLD_HOURS", 24)
    monkeypatch.setattr(deposit_sla.settings, "AUTO_CANCEL_EXPIRED_DEPOSIT", False)

    first = deposit_sla.process_deposit_sla(db)
    second = deposit_sla.process_deposit_sla(db)

    assert first["reminded_2h"] == 1
    assert first["reminded_20h"] == 1
    assert first["stock_released"] == 1
    assert second["reminded_2h"] == 0
    assert second["reminded_20h"] == 0
    assert second["stock_released"] == 0
    assert sent == [2, 20]
    assert released == [1]
    assert order.deposit_hold_overdue is True


def test_routine_admin_status_requires_reason_and_records_override(monkeypatch):
    order = Order(
        id=9,
        order_code="DH009",
        customer_name="Khach",
        customer_phone="0900000000",
        customer_address="Ha Noi",
        fulfillment_source="vietnam",
        status=OrderStatus.CONFIRMED,
        admin_notes="Ghi chú cũ",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = order
    with pytest.raises(ValueError, match="override_reason"):
        admin_update_order(
            db, 9, OrderUpdate(status=OrderStatus.PROCESSING), admin_id=3
        )

    db.add.reset_mock()
    updated = admin_update_order(
        db,
        9,
        OrderUpdate(
            status=OrderStatus.PROCESSING,
            override_reason="Timeline cũ bị thiếu dữ liệu",
        ),
        admin_id=3,
    )
    assert getattr(updated.status, "value", updated.status) == OrderStatus.PROCESSING.value
    assert "[Ghi đè trạng thái]" in updated.admin_notes
    audit = db.add.call_args.args[0]
    assert audit.from_status == "confirmed"
    assert audit.to_status == "processing"
    assert audit.admin_id == 3


def test_vietnam_stock_reserve_release_and_delivered_deduct(monkeypatch):
    product = Product(id=15, product_id="VN15", name="Hang VN", price=Decimal("100000"), available=5)
    product.warehouse_reserved = 0
    item = OrderItem(
        id=2,
        product_id=15,
        product=product,
        product_name="Hang VN",
        unit_price=Decimal("100000"),
        total_price=Decimal("200000"),
        quantity=2,
        fulfillment_source="vietnam",
        is_warehouse_item=True,
    )
    order = Order(
        id=10,
        order_code="DH010",
        customer_name="Khach",
        customer_phone="0900000000",
        customer_address="Ha Noi",
        fulfillment_source="vietnam",
        status=OrderStatus.WAITING_DEPOSIT,
        items=[item],
    )
    db = MagicMock()
    monkeypatch.setattr(warehouse_stock, "_lock_product", lambda _db, _id: product)

    warehouse_stock.reserve_warehouse_stock_for_order(db, order)
    assert product.warehouse_reserved == 2
    assert item.warehouse_stock_reserved_at is not None

    warehouse_stock.release_warehouse_stock_for_order(db, order)
    assert product.warehouse_reserved == 0
    assert item.warehouse_stock_reserved_at is None

    order.status = OrderStatus.DELIVERED
    warehouse_stock.reserve_warehouse_stock_for_order(db, order)
    warehouse_stock.deduct_warehouse_stock_for_order(db, order)
    assert product.available == 3
    assert product.warehouse_reserved == 0
    assert item.warehouse_stock_deducted_at is not None


def test_admin_sla_warns_vietnam_delay_china_stall_and_missing_tracking():
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    vietnam = Order(
        id=21,
        order_code="DH021",
        customer_name="VN",
        customer_phone="0900000000",
        customer_address="Ha Noi",
        fulfillment_source="vietnam",
        status=OrderStatus.CONFIRMED,
        confirmed_at=old,
    )
    china = Order(
        id=22,
        order_code="DH022",
        customer_name="CN",
        customer_phone="0900000001",
        customer_address="Ha Noi",
        fulfillment_source="china",
        status=OrderStatus.SHIPPING,
    )
    active = OrderShipmentEvent(
        order_id=22,
        step_key="tq_preparing",
        title="TQ",
        status="active",
        sort_order=1,
        scheduled_at=old,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [active]

    enrich_admin_orders_sla(db, [vietnam, china])

    assert any("4 giờ" in warning for warning in vietnam.sla_warnings)
    assert any("24 giờ" in warning for warning in vietnam.sla_warnings)
    assert any("quá SLA" in warning for warning in china.sla_warnings)
    assert any("thiếu mã vận đơn" in warning for warning in china.sla_warnings)


def test_checkout_rolls_back_both_groups_when_stock_reserve_fails(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        vietnam = Product(
            product_id="ROLLBACK-VN",
            code="RB-VN",
            name="VN",
            price=200000,
            available=10,
            warehouse_reserved=0,
            deposit_require=False,
            link_default=None,
            is_warehouse_clearance=False,
        )
        china = Product(
            product_id="ROLLBACK-CN",
            code="RB-CN",
            name="CN",
            price=200000,
            available=10,
            warehouse_reserved=0,
            deposit_require=False,
            link_default="https://detail.1688.com/offer/1.html",
            is_warehouse_clearance=False,
        )
        db.add_all([vietnam, china])
        db.commit()

        def fail_reserve(*_args, **_kwargs):
            raise warehouse_stock.WarehouseStockError("Tồn kho vừa thay đổi")

        monkeypatch.setattr(
            warehouse_stock, "reserve_warehouse_stock_for_order", fail_reserve
        )
        payload = OrderCreate(
            customer_name="Khach test",
            customer_phone="0900000000",
            customer_email="rollback@example.com",
            customer_address="Ha Noi",
            payment_method=PaymentMethod.COD,
            items=[
                OrderItemCreate(product_id=vietnam.id, quantity=1),
                OrderItemCreate(product_id=china.id, quantity=1),
            ],
        )
        with pytest.raises(HTTPException):
            order_endpoints.create_order(payload, BackgroundTasks(), db, None)
        assert db.query(Order).count() == 0
    finally:
        db.close()
        engine.dispose()

