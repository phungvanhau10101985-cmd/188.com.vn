"""Unit tests — Meta CAPI Purchase payload (server-side)."""
import hashlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.facebook_capi import (
    build_purchase_custom_data,
    build_purchase_user_data,
    fold_meta_text,
    geo_from_address,
    is_valid_meta_fbc,
    meta_purchase_event_id,
    normalize_capi_user_data,
    order_eligible_for_meta_purchase,
    split_vn_name,
)
from app.services.site_embed_templates import expand_facebook_pixel


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
    assert ud["em"] == [_sha("test@example.com")]
    assert ud["ph"] == [_sha("84901234567")]
    assert ud["country"] == [_sha("vn")]


def test_build_purchase_user_data_includes_click_id_and_geo():
    order = SimpleNamespace(
        customer_email="a@b.com",
        customer_phone="0901234567",
        customer_name="Nguyễn Văn An",
        customer_address="12 Nguyễn Huệ, Quận 1, Hồ Chí Minh",
        user_id=7,
        user=SimpleNamespace(gender="female", date_of_birth=date(1994, 5, 20)),
        meta_ads_context={
            "fbp": "fb.1.1710000000.1234567890",
            "fbc": "fb.1.1710000000.IwAR0clickid",
            "client_ip_address": "203.0.113.10",
            "client_user_agent": "Mozilla/5.0",
            "st": "ho chi minh",
            "ct": "quan 1",
            "external_id": "7",
        },
    )
    ud = build_purchase_user_data(order)
    assert ud["fbc"] == "fb.1.1710000000.IwAR0clickid"
    assert ud["fbp"] == "fb.1.1710000000.1234567890"
    assert ud["client_ip_address"] == "203.0.113.10"
    assert ud["fn"] == [_sha("van an")]
    assert ud["ln"] == [_sha("nguyen")]
    assert ud["st"] == [_sha("ho chi minh")]
    assert ud["ct"] == [_sha("quan 1")]
    assert ud["ge"] == [_sha("f")]
    assert ud["db"] == [_sha("19940520")]
    assert ud["external_id"] == [_sha("7")]


def test_normalize_capi_user_data_does_not_rehash_or_keep_invalid_fbc():
    hashed_em = _sha("user@example.com")
    out = normalize_capi_user_data(
        {
            "em": hashed_em,
            "fbc": "not-a-click-id",
            "fbp": "fb.1.1.1",
            "country": "vn",
        }
    )
    assert out["em"] == [hashed_em]
    assert "fbc" not in out
    assert out["fbp"] == "fb.1.1.1"
    assert out["country"] == [_sha("vn")]


def test_geo_from_address_reads_district_and_province():
    ct, st = geo_from_address("12 Nguyễn Huệ, Quận 1, Hồ Chí Minh")
    assert st == "ho chi minh"
    assert ct == "quan 1"


def test_split_vn_name_and_fold():
    fn, ln = split_vn_name("Nguyễn Văn A")
    assert ln == "nguyen"
    assert fn == "van a"
    assert fold_meta_text("Hà Nội") == "ha noi"


def test_is_valid_meta_fbc():
    assert is_valid_meta_fbc("fb.1.1710000000.IwAR0abc-def")
    assert not is_valid_meta_fbc("IwAR0abc")


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


def test_facebook_pixel_snippet_captures_fbclid():
    html = "".join(h for _, h in expand_facebook_pixel("123456789012345"))
    assert "fbclid" in html
    assert "_fbc" in html
    assert "window.__188FbPixelId='123456789012345'" in html
    assert "autoConfig:false" in html
