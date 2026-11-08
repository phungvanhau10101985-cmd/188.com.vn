"""Nhãn sale không được đè phân khúc giá trên custom_label_0."""

from datetime import date

from app.models.product import Product
from app.services.merchant_feed_tsv import TSV_COLUMNS, merchant_row_values
from app.services.sale_calendar import SaleCalendarState
from app.services.social_catalog_feed_tsv import META_TSV_COLUMNS, meta_row_values


def _product(**kwargs) -> Product:
    p = Product()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _state(phase: str | None) -> SaleCalendarState:
    return SaleCalendarState(
        phase=phase,
        enabled=True,
        event_date=date(2026, 11, 11),
        event_label="Sale 11/11",
        discount_percent=6.0,
        teaser_days=3,
        active_start_at=None,
        active_end_at=None,
        countdown_to=None,
    )


def _gmc(product: Product, phase: str | None) -> dict[str, str]:
    row = merchant_row_values(
        product,
        "https://188.com.vn",
        "https://188.com.vn",
        "VND",
        sale_state=_state(phase),
    )
    return {name: row[i] for i, name in enumerate(TSV_COLUMNS)}


def test_price_band_stays_on_custom_label_0_during_sale():
    p = _product(
        name="Áo sơ mi nam",
        product_id="P1",
        price=500_000,
        style="công sở",
        occasion="đi làm",
        subcategory="Áo sơ mi Nam",
        purchases=30,
        is_warehouse_clearance=False,
    )
    idle = _gmc(p, None)
    teaser = _gmc(p, "teaser")
    active = _gmc(p, "active")

    assert idle["custom_label_0"] == "Nhãn tùy chỉnh 2"
    assert teaser["custom_label_0"] == "Nhãn tùy chỉnh 2"
    assert active["custom_label_0"] == "Nhãn tùy chỉnh 2"

    assert idle["custom_label_2"] == "đi làm"
    assert teaser["custom_label_2"] == "sap_giam_gia"
    assert active["custom_label_2"] == "dang_giam_gia"

    assert teaser["custom_label_1"] == "công sở"
    assert active["custom_label_3"] == "moving"
    assert active["custom_label_4"] == "Áo sơ mi Nam"


def test_warehouse_label_survives_sale_status():
    p = _product(
        name="Áo thanh lý",
        product_id="P2",
        price=200_000,
        is_warehouse_clearance=True,
        subcategory="Áo thun Nam",
    )
    row = _gmc(p, "active")
    assert row["custom_label_0"] == "Nhãn tùy chỉnh 1"
    assert row["custom_label_1"] == "thanh_ly_kho"
    assert row["custom_label_2"] == "dang_giam_gia"


def test_meta_feed_uses_the_same_sale_label_slot():
    p = _product(name="Giày", product_id="P3", price=800_000, occasion="dạo phố")
    row = meta_row_values(
        p,
        "https://188.com.vn",
        "https://188.com.vn",
        "VND",
        fb_product_category="",
        google_product_category_default="",
        sale_state=_state("teaser"),
    )
    cols = {name: row[i] for i, name in enumerate(META_TSV_COLUMNS)}
    assert cols["custom_label_0"] == "Nhãn tùy chỉnh 3"
    assert cols["custom_label_2"] == "sap_giam_gia"
