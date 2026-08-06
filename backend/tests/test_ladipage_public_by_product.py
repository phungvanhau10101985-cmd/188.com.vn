# backend/tests/test_ladipage_public_by_product.py
from unittest.mock import MagicMock, patch

from app.api.endpoints import ladipage_public as pub


def test_get_published_ladipage_for_product_returns_response():
    db = MagicMock()
    lp = MagicMock()
    lp.id = 5
    lp.slug = "demo-ladipage"
    lp.title = "Demo"
    lp.meta_title = "Demo title"
    lp.meta_description = "Desc"
    lp.status = "published"
    lp.sections = []

    with patch("app.api.endpoints.ladipage_public.get_published_single_product_ladipage_slug", return_value="demo-ladipage"):
        with patch.object(db.query.return_value, "filter", return_value=db.query.return_value):
            db.query.return_value.filter.return_value.first.return_value = lp
            with patch("app.api.endpoints.ladipage_public.is_single_product_ladipage_for_product", return_value=True):
                with patch("app.api.endpoints.ladipage_public.resolve_products_for_ladipage", return_value=[MagicMock(id=99)]):
                    out = pub.get_published_ladipage_for_product(99, db)
    assert out.slug == "demo-ladipage"
    assert out.resolved_product_ids == [99]
