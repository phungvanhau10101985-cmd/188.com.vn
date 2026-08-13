"""Cổng API tra cứu vận chuyển — phân loại đầu vào, auth, payload."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.services import shipping_lookup as svc


def test_classify_order_code():
    assert svc.classify_query("DH042") == "order_code"
    assert svc.classify_query("dh1") == "order_code"
    assert svc.classify_query("DC009") == "order_code"


def test_classify_ems_code():
    assert svc.classify_query("EH042737692VN") == "ems_code"
    assert svc.classify_query("eh042737692vn") == "ems_code"


def test_classify_phone():
    assert svc.classify_query("0901234567") == "phone"
    assert svc.classify_query("0369597965") == "phone"
    assert svc.classify_query("369597965") == "phone"
    assert svc.classify_query("+84 901 234 567") == "phone"
    assert svc.classify_query("84901234567") == "phone"


def test_normalize_vn_phone_strips_leading_zero():
    assert svc.normalize_vn_phone("0369597965") == "369597965"
    assert svc.normalize_vn_phone("369597965") == "369597965"
    assert svc.normalize_vn_phone("0901234567") == "901234567"
    assert svc.normalize_vn_phone("901234567") == "901234567"
    assert svc.normalize_vn_phone("+84369597965") == "369597965"
    assert svc.normalize_vn_phone("84369597965") == "369597965"
    assert svc.normalize_vn_phone("0369 597 965") == "369597965"
    assert svc.phone_last9("0369597965") == svc.normalize_vn_phone("369597965")


def test_recipient_label_matches_phone_with_or_without_leading_zero():
    label_no_zero = "Lương Văn Thiện · 369597965 — Mỏ đá vôi Lý Quốc, Cao Bằng"
    label_with_zero = "Lương Văn Thiện · 0369597965 — Mỏ đá vôi Lý Quốc, Cao Bằng"
    for label in (label_no_zero, label_with_zero):
        assert svc.recipient_label_matches_phone(label, "0369597965")
        assert svc.recipient_label_matches_phone(label, "369597965")
    assert not svc.recipient_label_matches_phone(label_no_zero, "0901234567")


def test_serialize_order_includes_status_label_and_items():
    item = SimpleNamespace(
        product_id=11,
        product_name="Áo thun",
        product_image="https://cdn.example/a.jpg",
        product_slug="ao-thun",
        product_code="C0156",
        product_sku="C0156/XL",
        unit_price=150000,
        quantity=2,
        total_price=300000,
        selected_size="XL",
        selected_color="den",
        selected_color_name="Đen",
    )
    order = SimpleNamespace(
        id=42,
        order_code="DH042",
        status="shipping",
        payment_method="cod",
        payment_status="pending",
        customer_name="Nguyen Van A",
        customer_phone="0901234567",
        customer_email="a@example.com",
        customer_address="Hà Nội",
        shipping_address=None,
        customer_note="Giao giờ hành chính",
        shipping_method="EMS",
        shipping_provider="EMS",
        tracking_number="EH042737692VN",
        subtotal=300000,
        shipping_fee=0,
        discount_amount=0,
        wallet_amount_used=0,
        total_amount=300000,
        requires_deposit=False,
        deposit_amount=0,
        deposit_paid=0,
        remaining_amount=300000,
        estimated_delivery=None,
        actual_delivery=None,
        created_at=datetime(2026, 8, 1, 10, 0, 0),
        deposit_paid_at=None,
        confirmed_at=None,
        shipped_at=datetime(2026, 8, 10, 9, 0, 0),
        delivered_at=None,
        completed_at=None,
        cancelled_at=None,
        returned_at=None,
        items=[item],
    )
    data = svc.serialize_order(order)
    assert data["order_code"] == "DH042"
    assert data["status"] == "shipping"
    assert data["status_label"] == "Đang giao hàng"
    assert data["tracking_number"] == "EH042737692VN"
    assert data["items"][0]["product_name"] == "Áo thun"
    assert data["items"][0]["quantity"] == 2


def test_serialize_ems_tracking_keeps_event_order_and_fields():
    traced = datetime(2026, 8, 12, 14, 30, 0)
    payload = svc.serialize_ems_tracking(
        {
            "available": True,
            "tracking_code": "EH042737692VN",
            "reference_code": "REF1",
            "customer_code": "KH01",
            "weight_grams": "500",
            "receiver_address": "Hà Nội",
            "current_status": None,
            "current_status_description": "Phát thành công",
            "events": [
                {
                    "status_code": None,
                    "description": "Phát thành công",
                    "address": "Bưu cục Hà Nội",
                    "traced_at": traced,
                },
                {
                    "status_code": None,
                    "description": "Đang vận chuyển",
                    "address": "HCM",
                    "traced_at": datetime(2026, 8, 11, 8, 0, 0),
                },
            ],
            "error": None,
        }
    )
    assert payload["available"] is True
    assert payload["current_status_description"] == "Phát thành công"
    assert len(payload["events"]) == 2
    assert payload["events"][0]["description"] == "Phát thành công"
    assert payload["events"][0]["address"] == "Bưu cục Hà Nội"


def _request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode("latin-1"), v.encode("utf-8")) for k, v in headers.items()]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/v1/shipping/lookup",
            "headers": raw,
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )


def test_auth_missing_config_returns_503():
    with patch.object(svc.settings, "SHIPPING_LOOKUP_API_KEY", ""), patch(
        "app.services.shipping_lookup.issued_tokens", return_value=[]
    ):
        with pytest.raises(HTTPException) as exc:
            svc.verify_shipping_lookup_auth(_request({"x-api-key": "abc"}))
        assert exc.value.status_code == 503


def test_auth_accepts_x_api_key_and_bearer():
    with patch.object(svc.settings, "SHIPPING_LOOKUP_API_KEY", "secret-key-1"), patch(
        "app.services.shipping_lookup.issued_tokens", return_value=[]
    ):
        svc.verify_shipping_lookup_auth(_request({"x-api-key": "secret-key-1"}))
        svc.verify_shipping_lookup_auth(_request({"authorization": "Bearer secret-key-1"}))
        with pytest.raises(HTTPException) as exc:
            svc.verify_shipping_lookup_auth(_request({"x-api-key": "wrong"}))
        assert exc.value.status_code == 401


def test_auth_accepts_issued_file_key(tmp_path, monkeypatch):
    from app.services import shipping_lookup_keys as keys_svc

    monkeypatch.setattr(keys_svc, "keys_file", lambda: tmp_path / "shipping-lookup-keys.json")
    created = keys_svc.create_key("NanoAI")
    with patch.object(svc.settings, "SHIPPING_LOOKUP_API_KEY", ""):
        svc.verify_shipping_lookup_auth(_request({"x-api-key": created["token"]}))
        with pytest.raises(HTTPException) as exc:
            svc.verify_shipping_lookup_auth(_request({"x-api-key": "wrong"}))
        assert exc.value.status_code == 401


def test_lookup_by_order_code_not_found():
    db = MagicMock()
    with patch("app.services.shipping_lookup.order_crud.get_order_by_code", return_value=None):
        with pytest.raises(HTTPException) as exc:
            svc.lookup_by_order_code(db, "DH999")
        assert exc.value.status_code == 404
        assert exc.value.detail["ok"] is False
        assert "DH999" in exc.value.detail["detail"]
        assert exc.value.detail["query_type"] == "order_code"


def test_lookup_by_phone_not_found_is_business_404():
    db = MagicMock()
    with patch.object(svc, "get_latest_order_by_phone", return_value=None), patch.object(
        svc, "get_latest_ems_record_by_phone", return_value=None
    ):
        with pytest.raises(HTTPException) as exc:
            svc.lookup_by_phone(db, "0369597965")
        assert exc.value.status_code == 404
        assert exc.value.detail["ok"] is False
        assert exc.value.detail["query_type"] == "phone"
        assert exc.value.detail["query"] == "0369597965"
        assert "số điện thoại" in exc.value.detail["detail"]
        assert "Endpoint not found" not in exc.value.detail["detail"]


def test_lookup_by_phone_falls_back_to_ems_recipient_without_shop_order():
    db = MagicMock()
    record = SimpleNamespace(
        id=1921,
        order_id=None,
        order_code=None,
        ems_tracking_code="EH045793631VN",
        tracking_number_saved=None,
        updated_at=datetime(2026, 8, 11, 10, 0, 0),
        created_at=datetime(2026, 8, 11, 10, 0, 0),
        recipient_label="Lương Văn Thiện · 369597965 — Cao Bằng",
    )
    with patch.object(svc, "get_latest_order_by_phone", return_value=None), patch.object(
        svc, "get_latest_ems_record_by_phone", return_value=record
    ), patch.object(
        svc,
        "_build_payload",
        return_value={"ok": True, "query_type": "phone", "matched_by": "ems_recipient_phone"},
    ) as build:
        out = svc.lookup_by_phone(db, "0369597965")
    assert out["matched_by"] == "ems_recipient_phone"
    kwargs = build.call_args.kwargs
    assert kwargs["record"] is record
    assert kwargs["order"] is None
    assert kwargs["query_type"] == "phone"
    assert kwargs["matched_by"] == "ems_recipient_phone"
    assert kwargs["is_latest_order"] is True
    assert kwargs["fallback_ems_code"] == "EH045793631VN"


def test_lookup_shipping_routes_phone_and_ems():
    db = MagicMock()
    with patch.object(svc, "lookup_by_phone", return_value={"ok": True, "query_type": "phone"}) as phone_fn:
        out = svc.lookup_shipping(db, q="0901234567")
        assert out["query_type"] == "phone"
        phone_fn.assert_called_once()
    with patch.object(svc, "lookup_by_ems_code", return_value={"ok": True, "query_type": "ems_code"}) as ems_fn:
        out = svc.lookup_shipping(db, q="EH042737692VN")
        assert out["query_type"] == "ems_code"
        ems_fn.assert_called_once()
    with patch.object(svc, "lookup_by_order_code", return_value={"ok": True, "query_type": "order_code"}) as order_fn:
        out = svc.lookup_shipping(db, q="DH042")
        assert out["query_type"] == "order_code"
        order_fn.assert_called_once()


def test_lookup_shipping_explicit_ems_wins_over_q():
    db = MagicMock()
    with patch.object(svc, "lookup_by_ems_code", return_value={"ok": True, "query_type": "ems_code"}) as ems_fn:
        svc.lookup_shipping(db, q="DH042", ems_code="EH042737692VN")
        ems_fn.assert_called_once()


def test_lookup_by_ems_code_returns_live_events_without_shop_order():
    db = MagicMock()
    live = {
        "available": True,
        "tracking_code": "EH042737692VN",
        "current_status_description": "Đến bưu cục phát",
        "events": [
            {"description": "Đến bưu cục phát", "address": "Hà Nội", "traced_at": datetime(2026, 8, 12, 7, 0, 0)},
        ],
        "error": None,
    }
    with patch("app.services.shipping_lookup.find_ems_record_by_token", return_value=None), patch.object(
        svc, "_order_by_tracking", return_value=None
    ), patch.object(svc.ems_tracking_svc, "fetch_ems_tracking", return_value=live):
        payload = svc.lookup_by_ems_code(db, "EH042737692VN")
    assert payload["ok"] is True
    assert payload["query_type"] == "ems_code"
    assert payload["order"] is None
    assert payload["tracking_number"] == "EH042737692VN"
    assert payload["ems_tracking"]["events"][0]["description"] == "Đến bưu cục phát"


def test_lookup_by_ems_unknown_without_live_data_is_404():
    db = MagicMock()
    live = {"available": True, "tracking_code": "EH000000000VN", "events": [], "error": "Không tìm thấy"}
    with patch("app.services.shipping_lookup.find_ems_record_by_token", return_value=None), patch.object(
        svc, "_order_by_tracking", return_value=None
    ), patch.object(svc.ems_tracking_svc, "fetch_ems_tracking", return_value=live):
        with pytest.raises(HTTPException) as exc:
            svc.lookup_by_ems_code(db, "EH000000000VN")
        assert exc.value.status_code == 404
        assert "EH000000000VN" in exc.value.detail["detail"]
