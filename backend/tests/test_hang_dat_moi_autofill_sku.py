"""Tests parse mã đặt Hàng Đặt Mới (cột Q)."""
from app.services.google_sheets_hang_dat_moi_autofill import parse_order_sku_base


def test_parse_order_sku_accepts_base_and_slash_variants():
    assert parse_order_sku_base("C0156/") == "C0156"
    assert parse_order_sku_base("C0156/XL") == "C0156"
    assert parse_order_sku_base("C0156/XL/2") == "C0156"
    assert parse_order_sku_base("c0156/xl/2") == "C0156"
    assert parse_order_sku_base("H9287/39/1") == "H9287"
    assert parse_order_sku_base("  T0116/2XL/1  ") == "T0116"


def test_parse_order_sku_rejects_other_formats():
    assert parse_order_sku_base("") is None
    assert parse_order_sku_base("C0156") is None  # thiếu /
    assert parse_order_sku_base("ABC") is None
    assert parse_order_sku_base("0156") is None
    assert parse_order_sku_base("C015") is None
    assert parse_order_sku_base("C01566") is None
    assert parse_order_sku_base("CC0156") is None
    assert parse_order_sku_base("mã đặc biệt") is None
    assert parse_order_sku_base("ZALO") is None
    assert parse_order_sku_base("709384705862") is None


def test_autofill_columns_include_s_and_t():
    from app.services import google_sheets_hang_dat_moi_autofill as m

    assert m._COL_S == "S"
    assert m._COL_T == "T"
    assert m._COL_U == "U"
    assert m._COL_W == "W"
    assert m._COL_AB == "AB"
