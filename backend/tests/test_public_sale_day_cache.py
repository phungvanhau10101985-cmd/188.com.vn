"""Sale công khai giữ trong RAM theo ngày, không mở database lần sau."""

from app.services.sale_calendar import (
    SaleCalendarState,
    invalidate_public_sale_state_cache,
    public_sale_state_if_fresh,
    vn_today_key,
)
from app.services import sale_calendar as sale_mod


def test_public_sale_state_reused_until_the_day_changes():
    invalidate_public_sale_state_cache()
    state = SaleCalendarState(
        phase=None,
        enabled=True,
        event_date=None,
        event_label=None,
        discount_percent=0,
        teaser_days=3,
        active_start_at=None,
        active_end_at=None,
        countdown_to=None,
    )
    sale_mod._store_public_sale_state(state)
    assert public_sale_state_if_fresh() is state
    sale_mod._public_sale_state_cache = ("1999-01-01", state)
    assert public_sale_state_if_fresh() is None
    invalidate_public_sale_state_cache()
    assert vn_today_key()
