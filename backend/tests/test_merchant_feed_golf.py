from app.models.product import Product
from app.services.merchant_feed_tsv import (
    TSV_COLUMNS,
    is_golf_merchant_product,
    merchant_row_values,
)


def _product(**kwargs) -> Product:
    p = Product()
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _row(product: Product) -> list[str]:
    return merchant_row_values(product, "https://188.com.vn", "https://188.com.vn", "VND")


def _col(row: list[str], name: str) -> str:
    return row[TSV_COLUMNS.index(name)]


def test_golf_bag_is_one_merchant_group():
    p = _product(
        name="Túi gậy golf PGM QB043",
        category="Thể thao & dã ngoại",
        subcategory="Dã ngoại cắm trại",
        sub_subcategory="túi ngủ du lịch giữ ấm",
        product_id="A1",
        price=500000,
    )
    assert is_golf_merchant_product(p)
    row = _row(p)
    assert _col(row, "product_type") == "Golf"
    assert _col(row, "google_product_category") == "Golf"


def test_golf_apparel_joins_same_group():
    p = _product(
        name="Áo polo nam dài tay golf PGM",
        category="Thời trang Nam",
        subcategory="Áo thun & polo Nam",
        product_id="A2",
        price=400000,
    )
    row = _row(p)
    assert _col(row, "product_type") == "Golf"
    assert _col(row, "google_product_category") == "Golf"


def test_rating_group_club_without_word_still_golf():
    p = _product(name="Magic Eye MG013 titan", group_rating=92, category="Thể thao & dã ngoại")
    assert is_golf_merchant_product(p)


def test_artificial_grass_without_golf_word_stays_out():
    p = _product(name="Cỏ nhân tạo sân vườn", group_rating=89, category="Thể thao & dã ngoại")
    assert not is_golf_merchant_product(p)


def test_non_golf_keeps_store_breadcrumb():
    p = _product(
        name="Áo thun nam basic",
        category="Thời trang Nam",
        subcategory="Áo thun & polo Nam",
        product_id="A3",
        price=200000,
    )
    assert not is_golf_merchant_product(p)
    row = _row(p)
    assert _col(row, "product_type") == "Thời trang Nam > Áo thun & polo Nam"
    assert _col(row, "google_product_category") == "Thời trang Nam > Áo thun & polo Nam"
