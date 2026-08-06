# backend/tests/test_behavior_snapshot_batch_enrich.py
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.warehouse_clearance import enrich_snapshot_product_data_batch


def test_batch_skips_already_enriched():
    db = MagicMock()
    out = enrich_snapshot_product_data_batch(
        db,
        [
            (1, {"name": "A", "warehouse_clearance": {"enabled": False}}),
            (2, {"name": "B", "warehouse_variants": []}),
        ],
    )
    assert out[1]["warehouse_clearance"]["enabled"] is False
    assert out[2]["warehouse_variants"] == []
    db.query.assert_not_called()


def test_batch_loads_products_once_and_calls_batched_enrich():
    db = MagicMock()
    row = SimpleNamespace(
        id=10,
        is_warehouse_clearance=False,
        shop_name_chinese="Shop A",
        slug="sp-10",
        name="Áo",
        price=100000,
        main_image="https://cdn/x.jpg",
        brand_name="Brand",
        product_id="SKU10",
    )
    db.query.return_value.filter.return_value.all.return_value = [row]

    with patch(
        "app.services.warehouse_clearance.enrich_listing_product_payloads_batched"
    ) as batched:
        out = enrich_snapshot_product_data_batch(db, [(10, {"name": "Áo"})])
        assert batched.call_count == 1
        pairs = batched.call_args[0][1]
        assert len(pairs) == 1
        assert pairs[0][1]["shop_name_chinese"] == "Shop A"
    assert out[10]["shop_name_chinese"] == "Shop A"
