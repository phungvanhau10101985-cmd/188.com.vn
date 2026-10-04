"""Giá từng mã không bị Excel, HTML, hay giá khóa Google ghi đè."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services.google_automated_discount import apply_google_discount_to_cart_line
from app.services.import_link_excel_batch import merge_import_excel_overlay_into_product_data
from app.services.import_vipomall_scraper import ImportVipomallError, scrape_vipomall_for_import
from app.services.variant_sale_price import selected_color_name_for_line


def test_excel_overlay_keeps_scraped_sku_prices():
    data = {
        "price": 830_000,
        "pro_lower_price": "77",
        "pro_high_price": "440",
        "cost_cny": 77,
        "colors": [
            {"name": "2W41-15GBN-AC220V", "price": 830_000},
            {"name": "2W41-50GBN-AC220V", "price": 3_940_000},
        ],
    }
    merge_import_excel_overlay_into_product_data(
        data,
        {
            "price": 1,
            "pro_lower_price": "10",
            "pro_high_price": "20",
            "shop_name": "Shop Excel",
            "cost_cny": 12.5,
        },
    )
    assert data["price"] == 830_000
    assert data["pro_lower_price"] == "77"
    assert data["pro_high_price"] == "440"
    assert data["cost_cny"] == 12.5
    assert data["shop_name"] == "Shop Excel"


def test_excel_overlay_keeps_price_when_only_pairs_are_priced():
    data = {
        "price": 500_000,
        "pro_lower_price": "40",
        "product_info": {
            "variants": {
                "price_pairs": [
                    {"color": "Đỏ", "size": "S", "price": 500_000},
                    {"color": "Đỏ", "size": "M", "price": 700_000},
                ]
            }
        },
    }
    merge_import_excel_overlay_into_product_data(
        data,
        {"price": 1, "pro_lower_price": "9"},
    )
    assert data["price"] == 500_000
    assert data["pro_lower_price"] == "40"


def test_excel_overlay_still_sets_single_price_without_sku_prices():
    data = {"price": 100, "pro_lower_price": "1", "colors": [{"name": "Đỏ", "img": "a.jpg"}]}
    merge_import_excel_overlay_into_product_data(
        data,
        {"price": 830_000, "pro_lower_price": "77"},
    )
    assert data["price"] == 830_000
    assert data["pro_lower_price"] == "77"


def test_scrape_vipomall_api_failure_does_not_use_playwright(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("api down")

    monkeypatch.setattr(
        "app.services.import_vipomall_scraper.fetch_vipomall_product_detail",
        boom,
    )
    called = {"n": 0}

    def playwright(*_args, **_kwargs):
        called["n"] += 1
        raise AssertionError("playwright")

    monkeypatch.setattr(
        "app.services.import_playwright_dispatch.run_import_playwright_sync",
        playwright,
    )
    with pytest.raises(ImportVipomallError, match="giá tệ từng mã"):
        scrape_vipomall_for_import(
            "https://vipomall.vn/san-pham/1217276629?platform_type=10&merchant_id=101"
        )
    assert called["n"] == 0


def test_selected_color_name_comes_from_quote_when_client_omits_it():
    product = SimpleNamespace(
        colors=[
            {
                "name": "2W41-15GBN-AC220V",
                "sku": "2W41-15GBN-AC220V",
                "price": 830_000,
                "price_cny": 77,
            }
        ],
        product_info={},
    )
    assert (
        selected_color_name_for_line(product, "2W41-15GBN-AC220V", None, None)
        == "2W41-15GBN-AC220V"
    )
    assert (
        selected_color_name_for_line(product, "2W41-15GBN-AC220V", None, "Khách gửi")
        == "Khách gửi"
    )


def _lock(price: float, prior: float) -> dict:
    until = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    return {
        "google_automated_discount": {
            "price": price,
            "prior_price": prior,
            "locked_until": until,
            "offer_id": "A1",
        }
    }


def test_google_lock_keeps_absolute_price_when_list_matches():
    sale, listed, _pd = apply_google_discount_to_cart_line(
        product=SimpleNamespace(product_id="A1"),
        unit_sale=1_210_000,
        list_original=1_210_000,
        product_data=_lock(1_149_500, 1_210_000),
    )
    assert sale == 1_149_500
    assert listed == 1_210_000


def test_google_lock_scales_onto_selected_variant_list():
    sale, listed, _pd = apply_google_discount_to_cart_line(
        product=SimpleNamespace(product_id="A1"),
        unit_sale=3_940_000,
        list_original=3_940_000,
        product_data=_lock(747_000, 830_000),
    )
    assert listed == 3_940_000
    assert sale == round(3_940_000 * 747_000 / 830_000)
