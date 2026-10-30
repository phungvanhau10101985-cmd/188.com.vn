from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.crud.holiday_theme import describe_holiday_program, normalize_theme
from app.schemas.holiday_theme import HolidayOccasionUpdate, HolidayThemeAdminUpdate
from app.services import sale_calendar as sale_calendar_svc
from app.services.holiday_schedule import CATALOG, resolve_visible_holiday


def test_holiday_theme_update_accepts_tet_and_off():
    assert HolidayThemeAdminUpdate(active_theme="tet").active_theme == "tet"
    assert HolidayThemeAdminUpdate(active_theme=None).active_theme is None


def test_shop_account_sees_only_its_admin_preview():
    from types import SimpleNamespace

    from app.services.holiday_preview_grant import shop_user_can_see_admin_preview

    admin = SimpleNamespace(is_active=True, linked_user_id=7, email="desk@example.com")
    linked = SimpleNamespace(id=7, email="shop@example.com")
    stranger = SimpleNamespace(id=8, email="other@example.com")
    assert shop_user_can_see_admin_preview(admin, linked) is True
    assert shop_user_can_see_admin_preview(admin, stranger) is False
    same_email = SimpleNamespace(is_active=True, linked_user_id=None, email="Shop@Example.com")
    assert shop_user_can_see_admin_preview(same_email, SimpleNamespace(id=3, email="shop@example.com")) is True
    inactive = SimpleNamespace(is_active=False, linked_user_id=7, email="desk@example.com")
    assert shop_user_can_see_admin_preview(inactive, linked) is False


def test_naive_preview_expiry_is_vietnam_wall_clock_not_utc():
    """09:45 naive là giờ VN (02:45 UTC). Lúc 04:24 UTC bản xem trước 10 phút đã hết."""
    from app.services.holiday_preview_grant import coerce_preview_expiry

    naive = datetime(2026, 10, 30, 9, 45, 24)
    now = datetime(2026, 10, 30, 4, 24, tzinfo=timezone.utc)
    assert coerce_preview_expiry(naive, now=now) is None

    still = datetime(2026, 10, 30, 11, 35, 0)
    expected = int(datetime(2026, 10, 30, 4, 35, tzinfo=timezone.utc).timestamp())
    assert coerce_preview_expiry(still, now=now) == expected


def test_expired_naive_preview_row_is_cleared(monkeypatch):
    from types import SimpleNamespace

    from app.services.holiday_preview_grant import live_holiday_preview

    row = SimpleNamespace(
        preview_code="valentine",
        preview_admin_id=2,
        preview_expires_at=datetime(2026, 10, 30, 9, 45, 24),
    )
    db = SimpleNamespace(committed=False)

    def commit():
        db.committed = True

    db.commit = commit
    monkeypatch.setattr("app.crud.holiday_theme.get_singleton", lambda _db: row)
    now = datetime(2026, 10, 30, 4, 24, tzinfo=timezone.utc)
    assert live_holiday_preview(db, now=now) is None
    assert row.preview_code is None
    assert row.preview_admin_id is None
    assert row.preview_expires_at is None
    assert db.committed is True


def test_holiday_preview_token_roundtrip_and_rejects_tamper():
    from app.services.holiday_preview_grant import issue_holiday_preview_token, parse_holiday_preview_token

    token, expires_at = issue_holiday_preview_token("duong-lich", now=1_700_000_000)
    assert parse_holiday_preview_token(token, now=1_700_000_000) == ("duong-lich", expires_at)
    assert parse_holiday_preview_token(token, now=expires_at) is None
    flipped = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert parse_holiday_preview_token(flipped, now=1_700_000_000) is None


def test_holiday_theme_update_rejects_unknown():
    with pytest.raises(ValidationError):
        HolidayOccasionUpdate(code="christmas")


def test_normalize_theme_drops_unknown():
    assert normalize_theme("tet") == "tet"
    assert normalize_theme("  TET ") == "tet"
    assert normalize_theme("noel") is None
    assert normalize_theme(None) is None
    assert normalize_theme("") is None


def _tet_row(**overrides):
    data = dict(
        active_theme="tet",
        starts_on=date(2027, 2, 6),
        ends_on=date(2027, 2, 12),
        lead_days=4,
        sale_percent=15,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_holiday_window_teaser_then_active_then_off():
    row = _tet_row()
    before = describe_holiday_program(row, date(2027, 2, 1))
    assert before.mode == "upcoming"
    assert before.theme is None
    assert before.sale_phase is None

    teaser = describe_holiday_program(row, date(2027, 2, 3))
    assert teaser.mode == "teaser"
    assert teaser.theme == "tet"
    assert teaser.sale_phase == "teaser"
    assert teaser.window_start == date(2027, 2, 2)

    active = describe_holiday_program(row, date(2027, 2, 6))
    assert active.sale_phase == "active"
    assert active.theme == "tet"

    ended = describe_holiday_program(row, date(2027, 2, 13))
    assert ended.mode == "ended"
    assert ended.theme is None
    assert ended.sale_phase is None


def test_holiday_theme_stays_after_festival_without_sale():
    row = _tet_row(after_days=3)
    during = describe_holiday_program(row, date(2027, 2, 12))
    assert during.mode == "active"
    assert during.sale_phase == "active"
    assert during.window_end == date(2027, 2, 15)

    after = describe_holiday_program(row, date(2027, 2, 14))
    assert after.mode == "after"
    assert after.theme == "tet"
    assert after.sale_phase is None

    done = describe_holiday_program(row, date(2027, 2, 16))
    assert done.mode == "ended"
    assert done.theme is None


def test_holiday_without_percent_keeps_theme_but_not_sale():
    program = describe_holiday_program(_tet_row(sale_percent=0), date(2027, 2, 6))
    assert program.theme == "tet"
    assert program.sale_phase is None


def test_holiday_sale_state_replaces_calendar(monkeypatch):
    vn = timezone(timedelta(hours=7))
    holiday = sale_calendar_svc.SaleCalendarState(
        phase="active",
        enabled=True,
        event_date=date(2027, 2, 6),
        event_label="Sale Tết",
        discount_percent=15,
        teaser_days=4,
        active_start_at=datetime(2027, 2, 6, tzinfo=vn),
        active_end_at=datetime(2027, 2, 12, 23, 59, 59, tzinfo=vn),
        countdown_to=datetime(2027, 2, 12, 23, 59, 59, tzinfo=vn),
        kind="holiday",
    )
    monkeypatch.setattr(sale_calendar_svc, "maintain_sale_calendar_settings", lambda db: None)
    monkeypatch.setattr(sale_calendar_svc, "_holiday_sale_state", lambda db, today: holiday)
    state = sale_calendar_svc.resolve_sale_calendar_state(
        None,
        now=datetime(2027, 2, 6, 9, tzinfo=vn),
    )
    assert state.kind == "holiday"
    assert state.event_label == "Sale Tết"
    assert state.discount_percent == 15
    priced = sale_calendar_svc.apply_site_sale_to_price(100000, state)
    assert priced["phase"] == "active"
    assert priced["display_price"] == 85000


def test_inner_festival_day_interrupts_outer_then_returns():
    rules = list(CATALOG.values())
    tao = resolve_visible_holiday(rules, date(2027, 1, 30))
    assert tao is not None and tao.code == "tao-quan" and tao.mode == "active"
    back = resolve_visible_holiday(rules, date(2027, 1, 31))
    assert back is not None and back.code == "tet" and back.mode == "teaser"
    tet_day = resolve_visible_holiday(rules, date(2027, 2, 6))
    assert tet_day is not None and tet_day.code == "tet" and tet_day.mode == "active"
