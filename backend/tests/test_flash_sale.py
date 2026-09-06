"""Flash sale: trộn đều shop, % 8–12, không đụng hàng kho, không cộng chồng giá gốc."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.flash_sale import (
    FLASH_SALE_MAX_COUNT,
    FLASH_SALE_MAX_PERCENT,
    FLASH_SALE_MIN_PERCENT,
    apply_flash_percent_to_price,
    apply_flash_sale_to_payload,
    flash_percent_for_product,
    get_flash_sale_assignment,
    pick_even_shop_products,
    resolve_flash_slot,
    viewed_shop_l3_pairs,
)
from app.services.order_discounts import MAX_ORDER_DISCOUNT_PERCENT, apply_grand_discount_cap
from decimal import Decimal


def _p(id_, shop, subcategory="Áo", sub_subcategory="Áo thun"):
    return SimpleNamespace(
        id=id_,
        shop_name_chinese=shop,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        is_warehouse_clearance=False,
    )


def test_flash_percent_stays_in_8_to_12():
    percents = {flash_percent_for_product(i, "2026-09-06:4") for i in range(1, 400)}
    assert percents <= set(range(FLASH_SALE_MIN_PERCENT, FLASH_SALE_MAX_PERCENT + 1))
    assert len(percents) >= 3


def test_flash_percent_stable_for_same_slot():
    assert flash_percent_for_product(42, "2026-09-06:4") == flash_percent_for_product(
        42, "2026-09-06:4"
    )


def test_pick_even_does_not_drain_one_shop_first():
    queues = {
        "shop_a": [_p(i, "shop_a") for i in range(1, 20)],
        "shop_b": [_p(i, "shop_b") for i in range(100, 120)],
        "shop_c": [_p(i, "shop_c") for i in range(200, 220)],
    }
    picked = pick_even_shop_products(
        queues, ["shop_a", "shop_b", "shop_c"], target=12, seed=7
    )
    assert len(picked) == 12
    shops = [p.shop_name_chinese for p in picked]
    assert shops.count("shop_a") == 4
    assert shops.count("shop_b") == 4
    assert shops.count("shop_c") == 4
    # Không phải AAAAAAAA rồi mới tới shop khác.
    assert shops[:3] != ["shop_a", "shop_a", "shop_a"]


def test_pick_even_caps_at_twelve():
    queues = {"shop_a": [_p(i, "shop_a") for i in range(80)]}
    picked = pick_even_shop_products(queues, ["shop_a"], target=FLASH_SALE_MAX_COUNT, seed=1)
    assert len(picked) == FLASH_SALE_MAX_COUNT


def test_apply_flash_replaces_site_sale_not_warehouse():
    assignment = SimpleNamespace(
        product_ids=[10],
        percent_by_id={10: 11},
        percent_for=lambda pid: 11 if pid == 10 else None,
        slot=SimpleNamespace(end_at=datetime.now(timezone(timedelta(hours=7)))),
    )
    regular = {
        "id": 10,
        "price": 200_000,
        "is_warehouse_clearance": False,
        "site_sale": {"percent": 6, "phase": "teaser"},
    }
    apply_flash_sale_to_payload(regular, assignment, product_id=10)
    assert regular["flash_sale"]["percent"] == 11
    assert regular["site_sale"]["kind"] == "flash"
    assert regular["site_sale"]["percent"] == 11
    assert regular["original_price"] == 200_000
    assert regular["price"] == 178_000

    warehouse = {
        "id": 10,
        "price": 90_000,
        "is_warehouse_clearance": True,
        "warehouse_clearance_percent": 60,
    }
    apply_flash_sale_to_payload(
        warehouse,
        assignment,
        product=SimpleNamespace(is_warehouse_clearance=True, id=10),
        product_id=10,
    )
    assert "flash_sale" not in warehouse
    assert warehouse["price"] == 90_000


def test_flash_plus_birthday_still_caps_at_15_percent():
    list_subtotal = Decimal("200000")
    flash_savings = Decimal("22000")  # 11%
    welcome, birthday, loyalty, capped = apply_grand_discount_cap(
        list_subtotal=list_subtotal,
        site_sale_savings=flash_savings,
        welcome=Decimal("0"),
        birthday=Decimal("20000"),  # 10%
        loyalty=Decimal("0"),
    )
    assert capped is True
    assert welcome + birthday + loyalty + flash_savings <= (
        list_subtotal * MAX_ORDER_DISCOUNT_PERCENT / Decimal("100")
    ) + Decimal("1")
    assert birthday <= Decimal("8000")


def test_viewed_pairs_use_chinese_shop_and_level3_only():
    viewed = [
        _p(1, "Shop A", subcategory="Áo nam", sub_subcategory="Áo thun"),
        _p(2, "Shop A", subcategory="Áo nam", sub_subcategory="Áo sơ mi"),
        _p(3, "Shop B", subcategory="Quần", sub_subcategory="Áo thun"),
        _p(4, "Shop A", subcategory="Áo nam", sub_subcategory="Áo thun"),
        SimpleNamespace(
            id=5,
            shop_name_chinese="Shop C",
            subcategory="Kho",
            sub_subcategory="Áo thun",
            is_warehouse_clearance=True,
        ),
        _p(6, "Shop D", subcategory="Áo nam", sub_subcategory=""),
        _p(7, "", subcategory="Áo nam", sub_subcategory="Áo thun"),
    ]
    assert viewed_shop_l3_pairs(viewed) == [
        ("shop a", "áo thun"),
        ("shop a", "áo sơ mi"),
        ("shop b", "áo thun"),
    ]


def test_flash_slot_is_ten_minutes_from_midnight_vn():
    vn = timezone(timedelta(hours=7))
    noon = datetime(2026, 9, 6, 12, 7, tzinfo=vn)
    slot = resolve_flash_slot(noon)
    assert slot.start_at.hour == 12
    assert slot.start_at.minute == 0
    assert slot.end_at.hour == 12
    assert slot.end_at.minute == 10
    assert (slot.end_at - slot.start_at) == timedelta(minutes=10)


def test_apply_flash_percent_rounds_vnd():
    pricing = apply_flash_percent_to_price(199_000, 9)
    assert pricing["percent"] == 9
    assert pricing["display_price"] + pricing["savings_amount"] == 199_000
    assert pricing["event_label"] == "Flash sale"
    assert pricing["phase"] == "active"


def test_disabled_flash_returns_empty_assignment(monkeypatch):
    monkeypatch.setattr("app.services.flash_sale.is_flash_sale_enabled", lambda _db: False)
    assignment = get_flash_sale_assignment(SimpleNamespace(), user_id=1)
    assert assignment.product_ids == []
    assert assignment.percent_by_id == {}
