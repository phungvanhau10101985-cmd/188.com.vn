"""Fallback "phổ biến" khi rỗng: trộn round-robin bán chạy + được xem nhiều, cap subcategory
+ ép cân bằng 50/50 Nam/Nữ khi chưa có tín hiệu gì về khách (balance_gender=True)."""
from types import SimpleNamespace

from app.crud.popular_fallback import (
    POPULAR_FALLBACK_MAX_PER_SUBCATEGORY,
    _gender_tag,
    _interleave_and_diversify,
    _macro_interleave_two,
    _partition_by_gender,
)


def _p(id_, subcategory):
    return SimpleNamespace(id=id_, subcategory=subcategory)


def _pg(id_, subcategory, category="", sub_subcategory=""):
    """Product giả có category/subcategory/sub_subcategory — dùng cho test gắn nhãn giới tính."""
    return SimpleNamespace(
        id=id_, subcategory=subcategory, category=category, sub_subcategory=sub_subcategory
    )


def test_interleave_round_robin_order():
    bestsellers = [_p(1, "Giày"), _p(2, "Giày"), _p(3, "Túi")]
    most_viewed = [_p(4, "Áo"), _p(5, "Quần")]
    result = _interleave_and_diversify([bestsellers, most_viewed], limit=5)
    ids = [p.id for p in result]
    # Round-robin xen kẽ giữa 2 danh sách đã xếp hạng, không dồn hết 1 danh sách trước.
    assert ids == [1, 4, 2, 5, 3]


def test_interleave_dedupes_by_id_across_lists():
    bestsellers = [_p(1, "Giày"), _p(2, "Túi")]
    most_viewed = [_p(2, "Túi"), _p(3, "Áo")]  # id=2 trùng ở cả 2 danh sách
    result = _interleave_and_diversify([bestsellers, most_viewed], limit=10)
    ids = [p.id for p in result]
    assert ids.count(2) == 1
    assert set(ids) == {1, 2, 3}


def test_interleave_caps_per_subcategory():
    # 10 SP cùng subcategory "Giày" — chỉ tối đa POPULAR_FALLBACK_MAX_PER_SUBCATEGORY được chọn.
    bestsellers = [_p(i, "Giày") for i in range(1, 11)]
    result = _interleave_and_diversify(
        [bestsellers, []], limit=10, max_per_subcategory=POPULAR_FALLBACK_MAX_PER_SUBCATEGORY
    )
    assert len(result) == POPULAR_FALLBACK_MAX_PER_SUBCATEGORY


def test_interleave_respects_limit_even_with_many_subcategories():
    bestsellers = [_p(i, f"cat{i}") for i in range(1, 20)]
    result = _interleave_and_diversify([bestsellers, []], limit=7)
    assert len(result) == 7


def test_interleave_handles_missing_subcategory():
    bestsellers = [_p(1, None), _p(2, ""), _p(3, "  ")]
    result = _interleave_and_diversify([bestsellers, []], limit=10, max_per_subcategory=2)
    # None/rỗng gộp vào 1 bucket "_none" — vẫn bị cap như subcategory thật.
    assert len(result) == 2


def test_gender_tag_detects_nam_and_nu():
    assert _gender_tag(_pg(1, "Giày tây & công sở Nam")) == "nam"
    assert _gender_tag(_pg(2, "Giày cao gót Nữ")) == "nu"


def test_gender_tag_neutral_when_no_gender_word():
    assert _gender_tag(_pg(1, "Phụ kiện điện thoại")) == "neutral"


def test_gender_tag_neutral_when_both_present():
    # Cả 2 từ khóa cùng xuất hiện (ví dụ category chung "Phụ kiện Nam" nhưng subcategory
    # lại "Túi Nữ") -> không xác định rõ, coi là trung tính.
    assert _gender_tag(_pg(1, "Túi Nữ", category="Phụ kiện Nam")) == "neutral"


def test_partition_by_gender_groups_correctly():
    products = [
        _pg(1, "Giày tây & công sở Nam"),
        _pg(2, "Giày cao gót Nữ"),
        _pg(3, "Phụ kiện điện thoại"),
    ]
    buckets = _partition_by_gender(products)
    assert [p.id for p in buckets["nam"]] == [1]
    assert [p.id for p in buckets["nu"]] == [2]
    assert [p.id for p in buckets["neutral"]] == [3]


def test_macro_interleave_two_alternates_evenly():
    a = [_p(1, "x"), _p(2, "x"), _p(3, "x")]
    b = [_p(10, "y"), _p(20, "y")]
    result = _macro_interleave_two(a, b, limit=5)
    assert [p.id for p in result] == [1, 10, 2, 20, 3]


class _FakeHydrateDb:
    """Giả `db.query(Product).filter(...).all()` ở bước hydrate lại theo ID sau khi lấy
    thứ hạng từ cache — trả nguyên danh sách giả, không cần diễn giải điều kiện filter thật."""

    def __init__(self, products):
        self._products = products

    def query(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._products


def test_get_popular_fallback_products_balance_gender_is_50_50(monkeypatch):
    """balance_gender=True: đúng nửa Nam / nửa Nữ khi có đủ SP mỗi bên (mock DB session)."""
    import app.crud.popular_fallback as popular_fallback

    nam_products = [_pg(i, f"Giày Nam {i}") for i in range(1, 21)]
    nu_products = [_pg(100 + i, f"Giày Nữ {i}") for i in range(1, 21)]
    all_products = nam_products + nu_products

    def fake_fetch_ranked(db, *, order_exprs, exclude_ids, fetch_limit, join_target=None, join_condition=None):
        # bestsellers và most_viewed dùng cùng 1 pool giả cho đơn giản.
        return all_products

    # 2 danh sách hạng ID giờ đi qua cache dùng chung — xoá trước để không dính cache từ
    # lần gọi khác (test khác / lần gọi thật trước đó trong cùng process).
    popular_fallback.ttl_cache.invalidate("popular_fallback:bestsellers_ids")
    popular_fallback.ttl_cache.invalidate("popular_fallback:most_viewed_ids")

    monkeypatch.setattr(popular_fallback, "_fetch_ranked", fake_fetch_ranked)
    monkeypatch.setattr(popular_fallback, "_product_view_totals_subquery", lambda: SimpleNamespace(c=SimpleNamespace(view_total=0, product_id=None)))

    fake_db = _FakeHydrateDb(all_products)
    result = popular_fallback.get_popular_fallback_products(
        db=fake_db, exclude_product_ids=[], limit=20, balance_gender=True
    )
    tags = [_gender_tag(p) for p in result]
    assert len(result) == 20
    assert tags.count("nam") == 10
    assert tags.count("nu") == 10
