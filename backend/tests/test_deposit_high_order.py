from app.crud.deposit_settings import (
    order_hits_high_value,
    partial_percent_for_goods,
)


def test_default_threshold_stays_three_million():
    assert order_hits_high_value(2_000_000) is False
    assert order_hits_high_value(3_000_000) is True


def test_custom_threshold_uses_high_percent():
    assert order_hits_high_value(2_000_000, 2_000_000) is True
    assert order_hits_high_value(1_999_999, 2_000_000) is False
    assert partial_percent_for_goods(10, 2_000_000, 2_000_000) == 30
    assert partial_percent_for_goods(10, 1_500_000, 2_000_000) == 10
    assert partial_percent_for_goods(10, 3_000_000, 3_000_000, 25) == 25
    assert partial_percent_for_goods(40, 3_000_000, 3_000_000, 25) == 25
    assert partial_percent_for_goods(15, 2_999_999, 3_000_000, 25) == 15
