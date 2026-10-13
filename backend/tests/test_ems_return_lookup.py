"""Đối soát hoàn không lấy hành trình EMS từ mã vận đơn đang lưu trên đơn shop."""
from types import SimpleNamespace

from app.models.order import OrderStatus
from app.services.ems_shipment_import import (
    _ems_lookup_candidates,
    _ems_payload_belongs_to_reference,
    _saved_tracking_for_shipment,
    _shipment_order_status,
)


def test_lookup_does_not_use_order_tracking_of_another_code():
    order = SimpleNamespace(tracking_number="H30092609", status=OrderStatus.RETURNED.value)
    codes = _ems_lookup_candidates("H13102601", order)
    assert codes == ["H13102601"]


def test_lookup_keeps_ems_code_only_when_it_belongs_to_this_reference():
    own = _ems_lookup_candidates(
        "H30092609",
        known_ems_code="EH048812825VN",
        known_ems_reference="H30092609",
    )
    foreign = _ems_lookup_candidates(
        "H13102601",
        known_ems_code="EH048812825VN",
        known_ems_reference="H30092609",
    )
    assert own == ["H30092609", "EH048812825VN"]
    assert foreign == ["H13102601"]


def test_payload_of_another_reference_is_rejected():
    payload = {
        "tracking_code": "EH048812825VN",
        "reference_code": "H30092609",
        "events": [{"description": "Chuyển hoàn"}],
    }
    assert _ems_payload_belongs_to_reference(payload, "H30092609") is True
    assert _ems_payload_belongs_to_reference(payload, "EH048812825VN") is True
    assert _ems_payload_belongs_to_reference(payload, "H13102601") is False


def test_saved_shop_tracking_is_not_copied_onto_a_different_shipment():
    order = SimpleNamespace(tracking_number="H30092609")
    assert _saved_tracking_for_shipment(order, "H13102601", "EH048812825VN") is None
    assert _saved_tracking_for_shipment(order, "H30092609") == "H30092609"
    assert _saved_tracking_for_shipment(order, "EH048812825VN") is None
    assert (
        _saved_tracking_for_shipment(
            SimpleNamespace(tracking_number="EH048812825VN"),
            "H30092609",
            "EH048812825VN",
        )
        == "EH048812825VN"
    )


def test_returned_order_status_is_not_copied_onto_a_shipment():
    order = SimpleNamespace(status=OrderStatus.RETURNED.value)
    assert _shipment_order_status(order) is None
    shipping = SimpleNamespace(status=OrderStatus.SHIPPING.value)
    assert _shipment_order_status(shipping) == OrderStatus.SHIPPING.value
