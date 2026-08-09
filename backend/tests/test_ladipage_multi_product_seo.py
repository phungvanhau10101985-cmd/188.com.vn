"""Guardrail SEO + link chéo cho ladipage nhiều SP (canh theo danh mục chiếm đa số)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.ladipage_seo_strategy import (
    get_dominant_category_for_products,
    resolve_ladipage_category_competitor,
    suggest_multi_product_ladipage_title,
)


def test_suggest_multi_product_title_adds_usp():
    out = suggest_multi_product_ladipage_title("Oxford nam buộc dây", "Oxford nam buộc dây")
    assert "bộ sưu tập" in out.lower()
    assert out != "Oxford nam buộc dây"


def test_get_dominant_category_majority():
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.group_by.return_value = q
    # 8/10 sản phẩm cùng category_id=5 -> đa số (>=0.6)
    q.all.return_value = [(5, 8), (9, 2)]
    dominant = get_dominant_category_for_products(db, list(range(1, 11)))
    assert dominant == 5


def test_get_dominant_category_no_majority_returns_none():
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.group_by.return_value = q
    # Tản mác: không danh mục nào >=60%
    q.all.return_value = [(5, 4), (9, 4), (11, 2)]
    dominant = get_dominant_category_for_products(db, list(range(1, 11)))
    assert dominant is None


def test_resolve_competitor_for_multi_product_ladipage(monkeypatch):
    lp = SimpleNamespace(source_type="products", category_id=None, product_ids=[1, 2, 3])

    from app.services import ladipage_seo_strategy as strat

    monkeypatch.setattr(strat, "get_dominant_category_for_products", lambda db, ids: 42)
    monkeypatch.setattr(
        strat,
        "get_category_seo_competitor",
        lambda db, cat_id: {"category_id": cat_id, "category_name": "Oxford nam"} if cat_id else {},
    )
    db = MagicMock()
    result = resolve_ladipage_category_competitor(db, lp, [1, 2, 3])
    assert result["category_id"] == 42
    assert result["category_name"] == "Oxford nam"


def test_resolve_competitor_single_product_ladipage_returns_empty(monkeypatch):
    lp = SimpleNamespace(source_type="products", category_id=None, product_ids=[1])
    from app.services import ladipage_seo_strategy as strat

    monkeypatch.setattr(strat, "get_category_seo_competitor", lambda db, cat_id: {} if cat_id is None else {"category_id": cat_id})
    db = MagicMock()
    result = resolve_ladipage_category_competitor(db, lp, [1])
    assert result == {}
