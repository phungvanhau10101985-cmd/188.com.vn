"""Tra cứu bảng EMS theo SĐT (bỏ số 0 đầu)."""

from unittest.mock import MagicMock

from app.services.ems_shipment_import import _apply_search_filter


def test_search_filter_matches_phone_with_or_without_leading_zero():
    query = MagicMock()
    query.filter.return_value = query
    _apply_search_filter(query, "0369597965")
    query.filter.assert_called_once()
    compiled = str(query.filter.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "369597965" in compiled
    assert "recipient_label" in compiled.lower()

    query2 = MagicMock()
    query2.filter.return_value = query2
    _apply_search_filter(query2, "369597965")
    compiled2 = str(query2.filter.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "369597965" in compiled2


def test_search_filter_keeps_order_code_lookup():
    query = MagicMock()
    query.filter.return_value = query
    _apply_search_filter(query, "DH033")
    compiled = str(query.filter.call_args[0][0].compile(compile_kwargs={"literal_binds": True}))
    assert "DH033" in compiled.upper()
