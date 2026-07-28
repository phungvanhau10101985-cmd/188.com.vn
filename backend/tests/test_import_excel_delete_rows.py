"""Import Excel — dòng listed/AN=0 (xóa khỏi DB)."""

from unittest.mock import MagicMock

from app.crud.product import (
    _bulk_import_is_delete_row,
    _bulk_import_prefetch_delete_targets,
    excel_row_to_product,
)


def test_excel_row_to_product_listed_zero_is_minimal_stub():
    row = {
        "id": "A988248307692a188Y1273",
        "name": "Quần cashmere — không cần khi xóa",
        "Variant": '[{"name":"Đen","img":"https://example.com/x.jpg"}]',
        "listed": 0,
    }
    out = excel_row_to_product(row)
    assert out == {
        "product_id": "A988248307692a188Y1273",
        "excel_import_listed": 0,
    }
    assert "colors" not in out
    assert "slug" not in out


def test_bulk_import_is_delete_row():
    assert _bulk_import_is_delete_row({"excel_import_listed": 0}) is True
    assert _bulk_import_is_delete_row({"excel_import_listed": 1}) is False


def test_bulk_import_prefetch_delete_targets():
    db = MagicMock()
    p = MagicMock()
    p.product_id = "A123a188K0001"
    db.query.return_value.filter.return_value.all.return_value = [p]
    rows = [{"product_id": "A123a188K0001", "excel_import_listed": 0}]
    out = _bulk_import_prefetch_delete_targets(db, rows, {})
    assert out["A123a188K0001"] is p
