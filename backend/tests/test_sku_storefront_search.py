from app.services.product_internal_sku import looks_like_internal_sku_search_query
from app.services.search_query_corrector import correct_search_query_via_ai


def test_looks_like_internal_sku_search_query_accepts_web_codes():
    assert looks_like_internal_sku_search_query("u9897") is True
    assert looks_like_internal_sku_search_query("U9897") is True
    assert looks_like_internal_sku_search_query("  k0842  ") is True


def test_looks_like_internal_sku_search_query_rejects_truncated_or_text():
    assert looks_like_internal_sku_search_query("U9") is False
    assert looks_like_internal_sku_search_query("u989") is False
    assert looks_like_internal_sku_search_query("áo thun") is False
    assert looks_like_internal_sku_search_query("u9897 dép") is False
    assert looks_like_internal_sku_search_query("") is False


def test_ai_corrector_does_not_rewrite_sku_query():
    assert correct_search_query_via_ai("u9897") is None
    assert correct_search_query_via_ai("U9897") is None
