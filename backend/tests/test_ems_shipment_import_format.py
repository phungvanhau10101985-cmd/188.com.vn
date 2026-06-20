"""Kiểm tra validation mẫu file import gửi EMS."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.services import ems_import_sample_templates as sample_tpl
from app.services.ems_shipment_import import (
    EmsShipmentImportFormatError,
    validate_ems_shipment_import_file,
)


def _listing_export_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["id", "sku", "origin", "brand", "name", "pro_content", "price"])
    ws.append(
        [
            "Id sản phẩm",
            "Mã sản phẩm",
            "Xuất xứ",
            "Thương hiệu",
            "Tên",
            "Mô tả sản phẩm",
            "Giá",
        ]
    )
    ws.append(
        [
            "A838902375036",
            "H9441/1",
            "Trung Quốc",
            "Lion Leiden",
            "Túi đeo hông",
            "Túi đeo hông nam da bò thật…",
            710000,
        ]
    )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def test_valid_ems_sample_passes_validation():
    content, _ = sample_tpl.build_ems_shipment_sample_xlsx()
    validate_ems_shipment_import_file(content, source_filename="file_gui_ems_mau.xlsx")


def test_listing_product_export_rejected_by_headers():
    with pytest.raises(EmsShipmentImportFormatError, match="export sản phẩm"):
        validate_ems_shipment_import_file(_listing_export_bytes())


def test_listing_filename_rejected_even_without_parse():
    content, _ = sample_tpl.build_ems_shipment_sample_xlsx()
    with pytest.raises(EmsShipmentImportFormatError, match="listing"):
        validate_ems_shipment_import_file(
            content,
            source_filename="listing_queue_products_e67f30b31fbc_20260620_082152.xlsx",
        )


def _shop_export_bytes(headers: list[str], data_row: list) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(data_row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def test_flex_header_80_percent_and_nine_columns_passes():
    # Thiếu DON_HANG (4/5 tiêu đề quan trọng = 80%), vẫn đủ 9 cột
    headers = [
        "MA_VAN_DON",
        "TEN_SP",
        "TRONG_LUONG",
        "TEN_KH",
        "DIA_CHI_KH",
        "SDT_KH",
        "COD",
        "MA_SP",
        "GHI_CHU",
    ]
    validate_ems_shipment_import_file(
        _shop_export_bytes(
            headers,
            ["EE111111111VN", "SP", 0.5, "A", "addr", "090", 100000, "H1/1", ""],
        )
    )


def test_flex_header_rejects_wrong_column_count():
    headers = ["MA_VAN_DON", "TEN_KH", "COD", "MA_SP", "DON_HANG"]
    with pytest.raises(EmsShipmentImportFormatError, match="Không nhận diện"):
        validate_ems_shipment_import_file(
            _shop_export_bytes(headers, ["EE1", "A", 100000, "H1", "DH1"]),
        )


def test_flex_header_rejects_below_80_percent_important():
    # 9 cột nhưng chỉ 3/5 tiêu đề quan trọng
    headers = [
        "MA_VAN_DON",
        "TEN_SP",
        "TRONG_LUONG",
        "COL_D",
        "COL_E",
        "COL_F",
        "COL_G",
        "COL_H",
        "COL_I",
    ]
    with pytest.raises(EmsShipmentImportFormatError, match="Không nhận diện"):
        validate_ems_shipment_import_file(
            _shop_export_bytes(
                headers,
                ["EE1", "SP", 0.5, "x", "y", "z", "a", "b", "c"],
            ),
        )
