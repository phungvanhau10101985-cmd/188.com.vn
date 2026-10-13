"""Nguồn hết hàng nhưng còn kho thanh lý: cất rồi xóa colors/sizes, trả lại khi có hàng."""
from types import SimpleNamespace

from app.services import source_variant_oos as svc


def _parent(**kwargs):
    data = {
        "is_warehouse_clearance": False,
        "code": "HN256",
        "product_id": "HN256",
        "colors": [{"name": "Đen", "value": "Đen"}],
        "sizes": ["M", "L"],
        "source_variant_snapshot": None,
        "available": 0,
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def test_stash_clears_source_variants_when_warehouse_remains(monkeypatch):
    product = _parent()
    monkeypatch.setattr(svc, "_parent_has_active_warehouse_stock", lambda *_a, **_k: True)

    assert svc.stash_source_variants_if_warehouse_remains(None, product) is True
    assert product.colors == []
    assert product.sizes == []
    assert product.source_variant_snapshot["colors"][0]["name"] == "Đen"
    assert product.source_variant_snapshot["sizes"] == ["M", "L"]


def test_stash_keeps_variants_when_warehouse_empty(monkeypatch):
    product = _parent()
    monkeypatch.setattr(svc, "_parent_has_active_warehouse_stock", lambda *_a, **_k: False)

    assert svc.stash_source_variants_if_warehouse_remains(None, product) is False
    assert product.colors[0]["name"] == "Đen"
    assert product.sizes == ["M", "L"]
    assert product.source_variant_snapshot is None


def test_stash_skips_warehouse_rows_and_empty_variants(monkeypatch):
    monkeypatch.setattr(svc, "_parent_has_active_warehouse_stock", lambda *_a, **_k: True)
    warehouse = _parent(is_warehouse_clearance=True)
    empty = _parent(colors=[], sizes=[])

    assert svc.stash_source_variants_if_warehouse_remains(None, warehouse) is False
    assert warehouse.colors[0]["name"] == "Đen"
    assert svc.stash_source_variants_if_warehouse_remains(None, empty) is False
    assert empty.source_variant_snapshot is None


def test_restore_puts_variants_back_and_clears_snapshot():
    product = _parent(
        colors=[],
        sizes=[],
        source_variant_snapshot={
            "colors": [{"name": "Đỏ", "value": "Đỏ"}],
            "sizes": ["XL"],
        },
    )

    assert svc.restore_source_variants(product) is True
    assert product.colors[0]["name"] == "Đỏ"
    assert product.sizes == ["XL"]
    assert product.source_variant_snapshot is None
    assert svc.restore_source_variants(product) is False


def test_in_stock_restores_and_oos_stashes(monkeypatch):
    monkeypatch.setattr(svc, "_parent_has_active_warehouse_stock", lambda *_a, **_k: True)
    product = _parent()

    svc.apply_source_stock_variant_policy(None, product, new_status="out_of_stock")
    assert product.colors == []
    assert product.source_variant_snapshot["sizes"] == ["M", "L"]

    svc.apply_source_stock_variant_policy(None, product, new_status="in_stock")
    assert product.sizes == ["M", "L"]
    assert product.colors[0]["name"] == "Đen"
    assert product.source_variant_snapshot is None


def test_error_status_does_not_touch_variants(monkeypatch):
    monkeypatch.setattr(svc, "_parent_has_active_warehouse_stock", lambda *_a, **_k: True)
    product = _parent()

    svc.apply_source_stock_variant_policy(None, product, new_status="error")
    assert product.sizes == ["M", "L"]
    assert product.source_variant_snapshot is None
