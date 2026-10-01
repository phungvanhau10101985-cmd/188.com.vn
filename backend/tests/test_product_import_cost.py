"""Giá nhập gốc: tệ lúc cào và giá Việt Nam — không đụng giá bán."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.crud.product import product_to_excel_row
from app.schemas.product import Product, ProductUpdate
from app.services.excel_importer import PRODUCT_EXCEL_EXPORT_COLUMNS
from app.services.product_import_cost import (
    assert_single_import_cost,
    cost_cny_backfill_value,
    scraped_cny_amount,
    stamp_scraped_cost_cny,
)


def test_scraped_cny_ignores_group_labels():
    assert scraped_cny_amount("146,00") == 146.0
    assert scraped_cny_amount("20¥") == 20.0
    assert scraped_cny_amount("giày tây nam g05") is None


def test_backfill_only_china_numeric_and_empty_cost():
    assert (
        cost_cny_backfill_value(
            origin="1688",
            link="https://detail.1688.com/offer/1.html",
            pro_lower_price="88.5",
            cost_cny=None,
        )
        == 88.5
    )
    assert (
        cost_cny_backfill_value(
            origin="Việt Nam",
            link="https://188.com.vn/product/a",
            pro_lower_price="88",
            cost_cny=None,
        )
        is None
    )
    assert (
        cost_cny_backfill_value(
            origin="1688",
            link="https://detail.1688.com/offer/1.html",
            pro_lower_price="giày tây nam g05",
            cost_cny=None,
        )
        is None
    )
    assert (
        cost_cny_backfill_value(
            origin="taobao",
            link=None,
            pro_lower_price="10",
            cost_cny=12,
        )
        is None
    )


def test_reject_both_import_costs():
    with pytest.raises(HTTPException):
        assert_single_import_cost(
            existing_cny=None,
            existing_vnd=1000,
            update_data={"cost_cny": 20},
        )
    assert_single_import_cost(
        existing_cny=None,
        existing_vnd=1000,
        update_data={"cost_cny": 20, "cost_vnd": None},
    )


def test_blank_cost_becomes_none():
    row = ProductUpdate(cost_cny="  ")
    assert row.cost_cny is None


def test_negative_cost_rejected():
    with pytest.raises(ValueError):
        ProductUpdate(cost_vnd=-1)


def test_stamp_writes_cny_without_touching_sale_price():
    payload = {
        "origin": "1688",
        "link_default": "https://detail.1688.com/offer/9.html",
        "pro_lower_price": "88.5",
        "price": 250000,
    }
    stamp_scraped_cost_cny(payload)
    assert payload["cost_cny"] == 88.5
    assert payload["price"] == 250000
    blocked = {
        "origin": "1688",
        "link_default": "https://detail.1688.com/offer/9.html",
        "cost_vnd": 100000,
        "pro_lower_price": "10",
    }
    stamp_scraped_cost_cny(blocked)
    assert "cost_cny" not in blocked


def test_public_product_schema_hides_import_cost():
    assert "cost_cny" not in Product.model_fields
    assert "cost_vnd" not in Product.model_fields


def test_catalog_export_appends_costs_and_keeps_cny_column_blank():
    assert PRODUCT_EXCEL_EXPORT_COLUMNS[-2:] == ["cost_cny", "cost_vnd"]
    assert PRODUCT_EXCEL_EXPORT_COLUMNS.index("pro_lower_price") < PRODUCT_EXCEL_EXPORT_COLUMNS.index("listed")

    product = SimpleNamespace(
        slug="giay-test",
        name="Giày test",
        product_id="P1",
        features=[],
        style="",
        group_rating=888,
        group_question=0,
        code="SKU",
        description="",
        price=250000,
        cost_cny=88.5,
        cost_vnd=None,
        sizes=[],
        colors=[],
        images=[],
        gallery=[],
        link_default="https://detail.1688.com/offer/1.html",
        video_link="",
        main_image="",
        likes=0,
        purchases=0,
        rating_total=0,
        question_total=0,
        rating_point=0,
        available=1,
        deposit_require=False,
        category="",
        subcategory="",
        sub_subcategory="",
        material="",
        color="",
        occasion="",
        weight="",
        product_info=None,
        chinese_name="",
        shop_name_chinese="",
        is_active=True,
        pro_lower_price="88.5",
        pro_high_price="90",
    )
    row = product_to_excel_row(product)
    assert row["price"] == 250000
    assert row["pro_lower_price"] == ""
    assert row["pro_high_price"] == ""
    assert row["cost_cny"] == 88.5
    assert row["cost_vnd"] == ""
