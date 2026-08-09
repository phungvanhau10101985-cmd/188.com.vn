"""Lọc chất liệu cho ladipage danh mục."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.ladipage_ai_service import (
    material_filter_match_key,
    normalize_material_filter,
    resolve_products_for_ladipage,
)


def test_normalize_material_filter():
    assert normalize_material_filter(None) is None
    assert normalize_material_filter("  ") is None
    assert normalize_material_filter("  Da bò  ") == "Da bò"
    assert material_filter_match_key("  Da Bò ") == "da bò"


def test_resolve_products_applies_material_filter():
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = [SimpleNamespace(id=1)]

    lp = SimpleNamespace(
        source_type="category",
        category_id=588,
        products_limit=12,
        material_filter="Da bò",
        product_ids=[],
    )
    rows = resolve_products_for_ladipage(db, lp)
    assert len(rows) == 1
    # filter được gọi ít nhất 2 lần: category/active rồi material
    assert q.filter.call_count >= 2
    q.order_by.assert_called()
    q.limit.assert_called_with(12)
