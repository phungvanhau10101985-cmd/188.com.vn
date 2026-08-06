# backend/tests/test_ladipage_copy_sanitize.py
from types import SimpleNamespace

from app.services.ladipage_ai_service import (
    _product_brief,
    _product_code_tokens,
    _sanitize_copy_for_ladipage,
)


def test_sanitize_copy_removes_product_codes():
    product = SimpleNamespace(
        product_id="A920025943011a188B0266",
        code="B0266",
        base_sku="HN256",
        name="Giày Loafer Nam Da Bò B0266 HN256",
        material="Da bò",
        style="",
        color="",
        occasion="",
        features=[],
        price=1000000,
    )
    codes = _product_code_tokens(product)
    assert "B0266" in codes
    cleaned = _sanitize_copy_for_ladipage(product.name, code_tokens=codes)
    assert "B0266" not in cleaned
    assert "HN256" not in cleaned
    assert "Giày Loafer Nam Da Bò" in cleaned


def test_product_brief_uses_sanitized_name():
    product = SimpleNamespace(
        product_id="HN256/XL",
        code="HN256",
        base_sku="HN256",
        name="Túi da HN256 cao cấp",
        material="Da",
        style="",
        color="",
        occasion="",
        features=[],
        price=500000,
    )
    brief = _product_brief(product)
    assert "HN256" not in brief["name"]
    assert "Túi da" in brief["name"]
