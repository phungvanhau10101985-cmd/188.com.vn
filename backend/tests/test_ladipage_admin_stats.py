# backend/tests/test_ladipage_admin_stats.py
from unittest.mock import MagicMock, patch

from app.services.ladipage_admin_stats import ladipage_admin_stats


def test_product_single_stats_shape():
    db = MagicMock()
    with patch(
        "app.services.ladipage_admin_stats._single_ladipage_product_ids",
        side_effect=[{1, 2, 3}, {1, 2}],
    ):
        db.query.return_value.filter.return_value.scalar.side_effect = [100, 5]
        out = ladipage_admin_stats(db, "product_single")
    assert out["active_products_total"] == 100
    assert out["products_with_ladipage"] == 3
    assert out["products_with_published_ladipage"] == 2
    assert out["products_without_ladipage"] == 97
    assert out["ladipage_pages_total"] == 5
