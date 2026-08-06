"""Tests — ladipage URLs in catalog feeds."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.ladipage_catalog_feed import build_published_ladipage_product_links
from app.services.merchant_feed_tsv import _product_canonical_link


def test_product_canonical_link_prefers_ladipage_url():
    product = SimpleNamespace(id=42, slug="giay-loafer", product_id="SP001")
    links = {42: "https://188.com.vn/lp/penny-loafer-nam"}
    assert (
        _product_canonical_link(product, "https://188.com.vn", ladipage_links=links)
        == "https://188.com.vn/lp/penny-loafer-nam"
    )


def test_product_canonical_link_falls_back_to_pdp():
    product = SimpleNamespace(id=7, slug="giay-loafer", product_id="SP007")
    link = _product_canonical_link(product, "https://188.com.vn", ladipage_links={99: "https://188.com.vn/lp/other"})
    assert link == "https://188.com.vn/products/giay-loafer"


@patch("app.services.ladipage_catalog_feed.resolve_products_for_ladipage")
def test_build_ladipage_links_maps_all_resolved_products(mock_resolve):
    lp_multi = SimpleNamespace(
        id=1,
        slug="penny-loafer-collection",
        status="published",
        published_at=None,
        updated_at=None,
    )
    lp_single = SimpleNamespace(
        id=2,
        slug="giay-loafer-don",
        status="published",
        published_at=None,
        updated_at=None,
    )
    p1 = SimpleNamespace(id=10)
    p2 = SimpleNamespace(id=11)
    p3 = SimpleNamespace(id=12)
    mock_resolve.side_effect = [[p1, p2], [p3]]

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [lp_multi, lp_single]

    links = build_published_ladipage_product_links(db, "https://188.com.vn")
    assert links[10] == "https://188.com.vn/lp/penny-loafer-collection"
    assert links[11] == "https://188.com.vn/lp/penny-loafer-collection"
    assert 12 not in links
