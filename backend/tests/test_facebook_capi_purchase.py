"""Unit tests — Meta CAPI Purchase payload (server-side)."""
from decimal import Decimal
from types import SimpleNamespace

from app.services.facebook_capi import (
    build_purchase_custom_data,
    build_purchase_user_data,
    meta_purchase_event_id,
    order_eligible_for_meta_purchase,
)


def test_meta_purchase_event_id():
    assert meta_purchase_event_id(42) == "Purchase_42"


def test_build_purchase_custom_data_uses_sheet_product_id():
    product = SimpleNamespace(product_id="DH024")
    line = SimpleNamespace(
        product_id=99,
        product=product,
        unit_price=Decimal("150000"),
        quantity=2,
        total_price=Decimal("300000"),
    )
    order = SimpleNamespace(
        id=1001,
        total_amount=Decimal("300000"),
        items=[line],
    )
    data = build_purchase_custom_data(order)
    assert data["currency"] == "VND"
    assert data["content_ids"] == ["DH024"]
    assert data["contents"] == [{"id": "DH024", "quantity": 2, "item_price": 150000.0}]
    assert data["num_items"] == 2
    assert data["value"] == 300000.0
    assert data["order_id"] == "1001"
    assert data["content_type"] == "product"


def test_build_purchase_custom_data_fallback_db_product_id():
    line = SimpleNamespace(
        product_id=77,
        product=None,
        unit_price=Decimal("50000"),
        quantity=1,
        total_price=Decimal("50000"),
    )
    order = SimpleNamespace(id=5, total_amount=Decimal("0"), items=[line])
    data = build_purchase_custom_data(order)
    assert data["content_ids"] == ["77"]
    assert data["value"] == 50000.0


def test_build_purchase_user_data_hashes_email_phone():
    order = SimpleNamespace(customer_email="Test@Example.com", customer_phone="0901234567")
    ud = build_purchase_user_data(order)
    assert "em" in ud and len(ud["em"]) == 1
    assert "ph" in ud and ud["ph"][0] != "0901234567"


def test_order_eligible_for_meta_purchase():
    ok = SimpleNamespace(
        requires_deposit=True,
        status="deposit_paid",
        deposit_paid=Decimal("100000"),
    )
    waiting = SimpleNamespace(
        requires_deposit=True,
        status="waiting_deposit",
        deposit_paid=Decimal("0"),
    )
    assert order_eligible_for_meta_purchase(ok) is True
    assert order_eligible_for_meta_purchase(waiting) is False
