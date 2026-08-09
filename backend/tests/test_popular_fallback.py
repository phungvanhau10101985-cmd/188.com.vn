"""Fallback "phổ biến" khi rỗng: trộn round-robin bán chạy + được xem nhiều, cap subcategory."""
from types import SimpleNamespace

from app.crud.popular_fallback import (
    POPULAR_FALLBACK_MAX_PER_SUBCATEGORY,
    _interleave_and_diversify,
)


def _p(id_, subcategory):
    return SimpleNamespace(id=id_, subcategory=subcategory)


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
