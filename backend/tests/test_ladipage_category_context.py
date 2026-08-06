"""Unit tests — ladipage category-aligned product picking for AI context."""
from types import SimpleNamespace

from app.services.ladipage_ai_service import (
    _category_keywords,
    _pick_category_aligned_products,
    _product_category_relevance_score,
)


def _product(name: str, *, purchases: int = 0, material: str = "Da bò") -> SimpleNamespace:
    return SimpleNamespace(
        id=purchases,
        name=name,
        purchases=purchases,
        material=material,
        style="",
        subcategory="",
        sub_subcategory="",
    )


def test_category_keywords_extracts_loafer_and_penny():
    keys = _category_keywords("Giày tây nam penny loafer")
    assert "giay" in keys
    assert "penny" in keys
    assert "loafer" in keys
    assert "nam" not in keys


def test_bag_scores_lower_than_shoe_for_loafer_category():
    category = "Giày tây nam penny loafer"
    keys = _category_keywords(category)
    bag = _product("Túi Đeo Chéo Nam Da Bò Vintage", purchases=999)
    shoe = _product("Giày Lười Nam Da Thật Penny Loafer Chiều Cao 3cm", purchases=10)
    assert _product_category_relevance_score(shoe, keys) > _product_category_relevance_score(bag, keys)


def test_pick_category_aligned_products_prefers_shoes_over_top_selling_bag():
    category = "Giày tây nam penny loafer"
    products = [
        _product("Túi Đeo Chéo Nam Da Bò Vintage Thời Trang", purchases=5000),
        _product("Giày Lười Nam Da Thật Penny Loafer Chiều Cao 3cm", purchases=900),
        _product("Giày Lười Penny Loafer Nam Da Mờ Chiều Cao 4cm", purchases=800),
        _product("Cặp Công Sở Nam Da Bò Đựng Laptop", purchases=700),
    ]
    aligned = _pick_category_aligned_products(products, category)
    assert "Giày" in aligned[0].name
    assert all("Giày" in p.name or "Penny" in p.name or "Loafer" in p.name for p in aligned[:2])
