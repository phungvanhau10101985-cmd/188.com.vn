"""Xác nhận đơn hoàn chỉ khớp mã EMS / mã tham chiếu — mã đơn chỉ để xem."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.order import OrderStatus
from app.models.order_shipment import EmsShippingRecord
from app.services.shipping_operations import (
    _record_shop_return_received_date,
    apply_shop_return_received_on_ems_record,
    evaluate_shop_return_entry,
    is_ems_record_shop_return_received,
    return_to_shop_label,
)
from app.services.shop_return_confirm import resolve_shop_return_input


def _record(**overrides):
    base = dict(
        id=7,
        order_code="DH31",
        order_id=None,
        ems_status="Phát hoàn",
        ems_phase=None,
        ems_tracking_code="EE123456789VN",
        reference_code="H11022207",
        ems_reference_code=None,
        shop_return_received_at=None,
        order_status="shipping",
        product_code=None,
        cod_amount=None,
        cod_settlement_status=None,
        sync_message=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_shop_order_code_is_not_a_match_key():
    with patch(
        "app.services.shop_return_confirm.find_ems_record_by_ems_or_reference",
        return_value=None,
    ):
        code, err, matched = resolve_shop_return_input(MagicMock(), "DH31")
        dc_code, dc_err, dc_matched = resolve_shop_return_input(MagicMock(), "dc36833")

    assert matched is False and code is None and err and "chỉ để xem" in err
    assert dc_matched is False and dc_code is None and dc_err and "chỉ để xem" in dc_err


def test_ems_match_keeps_order_code_for_display_only():
    with patch(
        "app.services.shop_return_confirm.find_ems_record_by_ems_or_reference",
        return_value=_record(order_code="dc36833"),
    ):
        code, err, matched = resolve_shop_return_input(MagicMock(), "EE123456789VN")

    assert matched is True
    assert err is None
    assert code == "DC36833"


def test_reference_without_shop_order_still_matches():
    with patch(
        "app.services.shop_return_confirm.find_ems_record_by_ems_or_reference",
        return_value=_record(order_code=None),
    ):
        code, err, matched = resolve_shop_return_input(MagicMock(), "H11022207")

    assert matched is True
    assert err is None
    assert code is None


def test_same_shipment_entered_as_ems_and_reference_counts_once():
    record = _record()
    seen: dict[str, int] = {}
    with patch(
        "app.services.shipping_operations.find_ems_record_by_ems_or_reference",
        return_value=record,
    ):
        first = evaluate_shop_return_entry(
            MagicMock(),
            {"row_number": 1, "raw": "EE123456789VN", "resolve_error": None},
            seen,
        )
        second = evaluate_shop_return_entry(
            MagicMock(),
            {"row_number": 2, "raw": "H11022207", "resolve_error": None},
            seen,
        )

    assert first["status"] == "ready_to_confirm"
    assert first["can_confirm"] is True
    assert first["order_code"] == "DH31"
    assert first["ems_record_id"] == 7
    assert second["status"] == "duplicate"


def test_confirm_stamps_only_the_matched_shipment():
    record = _record(order_id=3)
    order = SimpleNamespace(
        id=3,
        status="shipping",
        returned_at=None,
        admin_notes=None,
        processed_by=None,
        updated_at=None,
    )

    def query(model):
        if model is EmsShippingRecord:
            raise AssertionError("không được quét vận đơn khác theo mã đơn")
        found = MagicMock()
        found.filter.return_value.first.return_value = order
        return found

    db = MagicMock()
    db.query.side_effect = query
    with (
        patch("app.services.warehouse_stock.sync_warehouse_stock_on_status_change"),
        patch("app.services.shipping_operations.affiliate_svc.handle_order_status_change"),
    ):
        apply_shop_return_received_on_ems_record(db, record, admin_id=1)

    assert record.shop_return_received_at is not None
    assert order.status == OrderStatus.RETURNED.value
    assert is_ems_record_shop_return_received(record) is True


def test_cod_paid_delivery_is_not_counted_as_return_received():
    record = _record(
        order_status="returned",
        ems_status="Đã phát thành công . Người nhận:HẢO shop188 DH537",
        ems_phase="delivered",
        shop_return_received_at="2026-09-23T11:42:37",
        cod_settlement_status="matched",
        cod_amount=504000,
    )
    assert is_ems_record_shop_return_received(record) is False
    assert _record_shop_return_received_date(record) is None
    assert (
        return_to_shop_label(
            order_status="returned",
            ems_status=record.ems_status,
            shop_return_received_at=record.shop_return_received_at,
            ems_phase="delivered",
            cod_settlement_status="matched",
        )
        is None
    )


def test_delivered_sibling_without_cod_file_is_not_a_return():
    record = _record(
        order_status="returned",
        ems_status="Đã phát thành công . Người nhận:GA",
        ems_phase="delivered",
        shop_return_received_at="2026-09-25T11:40:31",
        cod_amount=1450000,
    )
    assert is_ems_record_shop_return_received(record) is False
    assert _record_shop_return_received_date(record) is None


def test_unknown_ems_inherited_from_returned_order_is_not_received():
    record = _record(
        order_status="returned",
        ems_status="Chưa có thông tin",
        ems_phase="unknown",
        shop_return_received_at="2026-09-30T13:52:48",
    )
    assert is_ems_record_shop_return_received(record) is False


def test_real_return_confirm_still_counts_on_received_date():
    record = _record(
        order_status="returned",
        ems_status="Chưa phát được. 4.Chuyển hoàn cho người gửi",
        ems_phase="unknown",
        shop_return_received_at=datetime(2026, 9, 22, 8, 44, tzinfo=timezone.utc),
    )
    assert is_ems_record_shop_return_received(record) is True
    assert _record_shop_return_received_date(record) is not None


def test_order_status_returned_without_this_shipment_confirm_does_not_count():
    record = _record(
        order_status="returned",
        ems_status="Chuyển hoàn cho người gửi",
        shop_return_received_at=None,
    )
    assert is_ems_record_shop_return_received(record) is False
    assert (
        return_to_shop_label(
            order_status="returned",
            ems_status=record.ems_status,
            shop_return_received_at=None,
            ems_phase=None,
        )
        == "Đơn hoàn chưa trả shop"
    )
