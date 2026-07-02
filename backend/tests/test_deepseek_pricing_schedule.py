"""Tests for DeepSeek peak/off-peak schedule."""

from datetime import datetime, timezone
from unittest.mock import patch

from app.services.deepseek_pricing_schedule import (
    deepseek_off_peak_hours_per_day,
    deepseek_peak_hours_per_day,
    deepseek_pricing_status_for_admin,
    is_deepseek_off_peak_utc,
    is_deepseek_peak_utc,
    seconds_until_deepseek_off_peak,
)


def test_off_peak_hours_count():
    assert deepseek_peak_hours_per_day() == 7
    assert deepseek_off_peak_hours_per_day() == 17


def test_peak_window_utc_morning():
    dt = datetime(2026, 7, 15, 2, 30, tzinfo=timezone.utc)
    assert is_deepseek_peak_utc(dt) is True
    assert is_deepseek_off_peak_utc(dt) is False
    assert 0 < seconds_until_deepseek_off_peak(dt) <= 90 * 60


def test_peak_window_utc_second_block():
    dt = datetime(2026, 7, 15, 7, 0, tzinfo=timezone.utc)
    assert is_deepseek_peak_utc(dt) is True


def test_off_peak_midday_utc():
    dt = datetime(2026, 7, 15, 11, 0, tzinfo=timezone.utc)
    assert is_deepseek_off_peak_utc(dt) is True
    assert seconds_until_deepseek_off_peak(dt) == 0


def test_off_peak_night_utc():
    dt = datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
    assert is_deepseek_off_peak_utc(dt) is True


def test_admin_banner_wait_when_peak_and_off_peak_only():
    with patch(
        "app.services.deepseek_pricing_schedule.is_deepseek_peak_utc", return_value=True
    ), patch(
        "app.services.deepseek_pricing_schedule.seconds_until_deepseek_off_peak", return_value=1800
    ):
        st = deepseek_pricing_status_for_admin(off_peak_only_enabled=True)
    assert st["peak_now"] is True
    assert st["banner_variant"] == "wait"
    assert st["banner_message_vi"]
    assert "chờ" in st["banner_message_vi"].lower()


def test_admin_banner_cost_when_peak_without_off_peak_only():
    with patch(
        "app.services.deepseek_pricing_schedule.is_deepseek_peak_utc", return_value=True
    ), patch(
        "app.services.deepseek_pricing_schedule.seconds_until_deepseek_off_peak", return_value=600
    ):
        st = deepseek_pricing_status_for_admin(off_peak_only_enabled=False)
    assert st["banner_variant"] == "cost"
    assert "×2" in (st["banner_message_vi"] or "")
