"""Thứ tự đánh giá trên trang sản phẩm: số hữu ích import theo từng sản phẩm."""

from types import SimpleNamespace

from app.api.endpoints.product_reviews import order_storefront_reviews
from app.services.rating_group_seed_reviews import SEED_USEFUL_MAX, SEED_USEFUL_MIN


def _review(rid, *, imported=True, mine=False, useful=0, voted=False):
    return SimpleNamespace(
        id=rid,
        is_imported=imported,
        is_current_user=mine,
        useful=useful,
        user_has_voted=voted,
        display_created_at=None,
        created_at=None,
    )


def test_imported_useful_varies_by_product_and_higher_stays_first():
    items = [_review(i, useful=200) for i in range(1, 31)]
    first = order_storefront_reviews(items, 101)
    again = order_storefront_reviews(items, 101)
    other = order_storefront_reviews(items, 202)

    assert [r.useful for r in first] == [r.useful for r in again]
    assert [r.id for r in first] == [r.id for r in again]
    assert [r.useful for r in first] != [r.useful for r in other]
    assert [r.useful for r in first] == sorted((r.useful for r in first), reverse=True)
    assert all(SEED_USEFUL_MIN <= r.useful <= SEED_USEFUL_MAX for r in first)
    assert all(item.useful == 200 for item in items)


def test_viewer_vote_adds_one_and_real_useful_stays():
    items = [
        _review(1, imported=True, useful=500),
        _review(2, imported=False, useful=3),
        _review(3, imported=False, mine=True, useful=1),
        _review(4, imported=True, useful=9, voted=True),
    ]
    ordered = order_storefront_reviews(items, 7)
    by_id = {r.id: r for r in ordered}
    assert [r.id for r in ordered[:2]] == [3, 2]
    assert by_id[2].useful == 3
    assert by_id[3].useful == 1
    plain = order_storefront_reviews([_review(4, useful=9)], 7)[0]
    assert by_id[4].useful == plain.useful + 1
    imported = [r for r in ordered if r.is_imported]
    assert [r.useful for r in imported] == sorted((r.useful for r in imported), reverse=True)
