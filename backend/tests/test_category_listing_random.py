"""Tests for category listing random (seeded shuffle toàn danh mục)."""

from app.services.category_listing_random import seeded_shuffle_product_ids


def test_seeded_shuffle_stable_for_same_seed():
    ids = list(range(1, 101))
    a = seeded_shuffle_product_ids(ids, "session-abc")
    b = seeded_shuffle_product_ids(ids, "session-abc")
    assert a == b
    assert sorted(a) == ids


def test_seeded_shuffle_differs_by_seed():
    ids = list(range(1, 51))
    a = seeded_shuffle_product_ids(ids, "seed-one")
    b = seeded_shuffle_product_ids(ids, "seed-two")
    assert a != b
    assert sorted(a) == ids
    assert sorted(b) == ids


def test_seeded_shuffle_pagination_slice_stable():
    ids = list(range(1, 201))
    seed = "paginate-test"
    ordered = seeded_shuffle_product_ids(ids, seed)
    page1 = ordered[0:48]
    page2 = ordered[48:96]
    assert len(set(page1) & set(page2)) == 0
    again = seeded_shuffle_product_ids(ids, seed)
    assert again[0:48] == page1
    assert again[48:96] == page2
