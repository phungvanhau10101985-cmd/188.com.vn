"""Tests — xóa ladipage 1 SP khi sản phẩm chính bị xóa."""

from types import SimpleNamespace

from app.services.ladipage_cleanup import is_single_product_ladipage_for_product


def _lp(source_type: str, product_ids):
    return SimpleNamespace(source_type=source_type, product_ids=product_ids)


def test_single_product_ladipage_match():
    lp = _lp("products", [42])
    assert is_single_product_ladipage_for_product(lp, 42) is True


def test_single_product_ladipage_wrong_id():
    lp = _lp("products", [42])
    assert is_single_product_ladipage_for_product(lp, 99) is False


def test_multi_product_ladipage_not_deleted():
    lp = _lp("products", [42, 43])
    assert is_single_product_ladipage_for_product(lp, 42) is False
    assert is_single_product_ladipage_for_product(lp, 43) is False


def test_category_ladipage_not_deleted():
    lp = _lp("category", [42])
    assert is_single_product_ladipage_for_product(lp, 42) is False
    assert is_single_product_ladipage_for_product(lp, 99) is False


def test_single_product_ladipage_accepts_string_id_in_json():
    lp = _lp("products", ["42"])
    assert is_single_product_ladipage_for_product(lp, 42) is True


def test_get_published_slug_prefers_single_product_ladipage():
    from types import SimpleNamespace

    from app.services.ladipage_cleanup import get_published_single_product_ladipage_slug

    published_single = SimpleNamespace(
        source_type="products",
        product_ids=[42],
        status="published",
        slug="lp-single",
        published_at=None,
        updated_at=None,
        id=1,
    )
    published_multi = SimpleNamespace(
        source_type="products",
        product_ids=[42, 43],
        status="published",
        slug="lp-multi",
        published_at=None,
        updated_at=None,
        id=2,
    )

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeDb:
        def __init__(self, rows):
            self._rows = rows

        def query(self, model):
            return FakeQuery(self._rows)

    db = FakeDb([published_multi, published_single])
    assert get_published_single_product_ladipage_slug(db, 42) == "lp-single"
    assert get_published_single_product_ladipage_slug(db, 99) is None
