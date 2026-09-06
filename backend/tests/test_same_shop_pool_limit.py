"""
SAME_SHOP_MAX_POOL đủ dư so với shop lớn nhất (đã xác minh trên DB thật: 1199 SP active)
+ trọng số round-robin dùng đủ lịch sử xem (tối đa 40 lượt) thay vì chỉ 8 lượt gần nhất.
"""
from types import SimpleNamespace

from app.crud.user import (
    SAME_SHOP_MAX_POOL,
    SAME_SHOP_STREAK_THRESHOLD,
    _balance_same_shop_products,
    _build_same_shop_weighted_cycle,
)


def test_same_shop_max_pool_has_headroom_above_known_max_shop_size():
    # Shop lớn nhất trên DB production tại thời điểm sửa: 1199 SP active.
    assert SAME_SHOP_MAX_POOL >= 1199 * 1.2


def _product(id_, shop, sub_subcategory="áo thun"):
    return SimpleNamespace(
        id=id_,
        shop_name_chinese=shop,
        subcategory=None,
        sub_subcategory=sub_subcategory,
    )


def test_weighted_cycle_uses_full_history_not_just_recent_window():
    """
    3 lượt gần nhất đều shop_a (không đủ streak, ngưỡng streak là 8) — shop_b chỉ xuất hiện ở
    lượt xem cũ hơn (ngoài "recent"). Trước khi sửa: shop_b bị fetch vào candidate query nhưng
    không bao giờ được vòng quay round-robin chọn tới vì trọng số chỉ tính từ recent_product_ids.
    """
    assert SAME_SHOP_STREAK_THRESHOLD > 3  # đảm bảo test này không vô tình rơi vào nhánh streak

    product_by_id = {
        1: _product(1, "shop_a"),
        2: _product(2, "shop_a"),
        3: _product(3, "shop_a"),
        4: _product(4, "shop_b"),
    }
    recent_product_ids = [1, 2, 3]
    history_product_ids = [1, 2, 3, 4]
    history_shop_order = ["shop_a", "shop_b"]
    shops_lower = {"shop_a", "shop_b"}

    weighted_cycle, overrides = _build_same_shop_weighted_cycle(
        recent_product_ids,
        history_shop_order,
        product_by_id,
        shops_lower,
        history_product_ids=history_product_ids,
    )

    assert "shop_b" in weighted_cycle
    assert overrides == {}


def test_weighted_cycle_falls_back_to_recent_when_history_not_provided():
    """Tương thích ngược: không truyền history_product_ids -> dùng recent_product_ids như cũ."""
    product_by_id = {1: _product(1, "shop_a")}
    weighted_cycle, _ = _build_same_shop_weighted_cycle(
        [1], ["shop_a"], product_by_id, {"shop_a"}
    )
    assert weighted_cycle == ["shop_a"]


def test_weighted_cycle_streak_still_uses_recent_window_only():
    """Streak (ưu tiên 1 shop) vẫn phải dựa trên lượt xem GẦN NHẤT, không đổi bởi Phase 3.
    Cần có shop khác trong lịch sử để nhánh streak-dominant thực sự kích hoạt (nếu không có
    shop khác để xen vào, code rơi về nhánh trọng số thường)."""
    recent_product_ids = [1, 2, 3, 4, 5, 6, 7, 8]
    product_by_id = {i: _product(i, "shop_a") for i in recent_product_ids}
    product_by_id[9] = _product(9, "shop_b")
    history_shop_order = ["shop_a", "shop_b"]
    shops_lower = {"shop_a", "shop_b"}

    weighted_cycle, overrides = _build_same_shop_weighted_cycle(
        recent_product_ids,
        history_shop_order,
        product_by_id,
        shops_lower,
        history_product_ids=recent_product_ids + [9],
    )
    assert overrides.get("shop_a") is not None  # streak dominance override áp dụng
    assert "shop_b" in weighted_cycle  # vẫn xen shop khác đã xem trước đó


def test_balance_keeps_only_same_shop_and_level3():
    candidates = [
        _product(1, "shop_a", "áo thun"),
        _product(2, "shop_a", "quần short"),
        _product(3, "shop_b", "áo thun"),
        _product(4, "shop_a", "áo thun"),
    ]
    page, _ = _balance_same_shop_products(
        candidates,
        {("shop_a", "áo thun")},
        {"shop_a"},
        weighted_cycle=["shop_a"],
        shop_queue_order=["shop_a"],
        seed=1,
        page_size=8,
        offset=0,
        limit=8,
    )
    assert {p.id for p in page} == {1, 4}
