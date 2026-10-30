"""Lịch lễ lặp mỗi năm theo ngày/tháng. Không lưu năm.

Khi nhiều dịp trùng một ngày, ngày chính của dịp ngắn hơn được hiện.
Hết ngày đó thì quay lại dịp lớn đang bao bên ngoài.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Literal, Optional

from app.services.lunar_calendar import lunar_to_solar

CalendarKind = Literal["solar", "lunar"]


@dataclass(frozen=True)
class HolidayRule:
    code: str
    name: str
    calendar: CalendarKind
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    lead_days: int
    after_days: int
    sale_percent: float
    priority: int
    sale_label: str
    tagline: str
    summary: str
    enabled: bool = True


@dataclass(frozen=True)
class HolidayWindow:
    rule: HolidayRule
    core_start: date
    core_end: date
    window_start: date
    window_end: date


@dataclass(frozen=True)
class VisibleHoliday:
    code: str
    name: str
    mode: str
    sale_phase: Optional[str]
    sale_percent: float
    sale_label: str
    lead_days: int
    core_start: date
    core_end: date
    window_start: date
    window_end: date


def _catalog() -> tuple[HolidayRule, ...]:
    return (
        HolidayRule("duong-lich", "Tết Dương lịch", "solar", 1, 1, 1, 1, 5, 2, 6, 4, "Sale Tết dương", "Năm mới", "Đầu năm dương lịch.", True),
        HolidayRule("tao-quan", "Ông Công Ông Táo", "lunar", 12, 23, 12, 23, 0, 0, 6, 5, "Sale Ông Táo", "Đưa Táo về trời", "Đúng 23 tháng Chạp.", True),
        HolidayRule("tet", "Tết Nguyên Đán", "lunar", 1, 1, 1, 5, 7, 3, 12, 1, "Sale Tết", "Tết đang về", "Mùng 1 đến mùng 5. Bật trước 7 ngày nên trùng ngày Ông Táo.", True),
        HolidayRule("valentine", "Valentine", "solar", 2, 14, 2, 14, 0, 0, 8, 4, "Sale Valentine", "Mùa yêu", "Đúng 14/2.", True),
        HolidayRule("nguyen-tieu", "Tết Nguyên Tiêu", "lunar", 1, 15, 1, 15, 3, 1, 6, 5, "Sale Nguyên Tiêu", "Rằm tháng Giêng", "Rằm tháng Giêng.", True),
        HolidayRule("phu-nu-83", "Quốc tế Phụ nữ", "solar", 3, 8, 3, 8, 5, 1, 8, 4, "Sale 8/3", "8/3", "Quốc tế Phụ nữ.", True),
        HolidayRule("gio-to", "Giỗ Tổ Hùng Vương", "lunar", 3, 10, 3, 10, 5, 2, 6, 5, "Sale Giỗ Tổ", "Giỗ Tổ", "10 tháng 3 âm lịch.", True),
        HolidayRule("dai-le", "30/4 và 1/5", "solar", 4, 30, 5, 1, 7, 2, 8, 3, "Sale 30/4", "Đại lễ", "30/4 đến 1/5.", True),
        HolidayRule("thieu-nhi", "Quốc tế Thiếu nhi", "solar", 6, 1, 6, 1, 4, 0, 6, 5, "Sale 1/6", "1/6", "Quốc tế Thiếu nhi.", True),
        HolidayRule("doan-ngo", "Tết Đoan Ngọ", "lunar", 5, 5, 5, 5, 4, 1, 6, 5, "Sale Đoan Ngọ", "Đoan Ngọ", "5 tháng 5 âm lịch.", True),
        HolidayRule("vu-lan", "Lễ Vu Lan", "lunar", 7, 15, 7, 15, 5, 2, 5, 5, "Sale Vu Lan", "Vu Lan", "Rằm tháng 7.", True),
        HolidayRule("quoc-khanh", "Quốc khánh", "solar", 9, 2, 9, 3, 7, 2, 8, 3, "Sale Quốc khánh", "Quốc khánh", "2/9 và 3/9.", True),
        HolidayRule("trung-thu", "Tết Trung thu", "lunar", 8, 15, 8, 15, 7, 3, 10, 2, "Sale Trung thu", "Trung thu", "Rằm tháng 8.", True),
        HolidayRule("phu-nu-2010", "Phụ nữ Việt Nam", "solar", 10, 20, 10, 20, 7, 2, 8, 4, "Sale 20/10", "20/10", "Phụ nữ Việt Nam.", True),
        HolidayRule("nha-giao", "Nhà giáo Việt Nam", "solar", 11, 20, 11, 20, 7, 2, 8, 4, "Sale 20/11", "20/11", "Nhà giáo Việt Nam.", True),
        HolidayRule("giang-sinh", "Giáng sinh", "solar", 12, 24, 12, 25, 10, 6, 10, 2, "Sale Giáng sinh", "Mùa Giáng sinh", "24 và 25/12.", True),
    )


CATALOG: dict[str, HolidayRule] = {row.code: row for row in _catalog()}


def valid_month_day(kind: CalendarKind, month: int, day: int) -> bool:
    if not 1 <= month <= 12:
        return False
    if kind == "lunar":
        return 1 <= day <= 30
    if month == 2:
        return 1 <= day <= 29
    return 1 <= day <= calendar.monthrange(2023, month)[1]


def _anchor(kind: CalendarKind, month: int, day: int, year: int) -> Optional[date]:
    if kind == "solar":
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return lunar_to_solar(day, month, year, 0)


def _core_span(rule: HolidayRule, year: int) -> Optional[tuple[date, date]]:
    start = _anchor(rule.calendar, rule.start_month, rule.start_day, year)
    end = _anchor(rule.calendar, rule.end_month, rule.end_day, year)
    if start is None or end is None:
        return None
    if end < start:
        end_next = _anchor(rule.calendar, rule.end_month, rule.end_day, year + 1)
        if end_next is None:
            return None
        end = end_next
    return start, end


def windows_covering(rule: HolidayRule, today: date) -> list[HolidayWindow]:
    lead = max(0, min(60, int(rule.lead_days or 0)))
    after = max(0, min(60, int(rule.after_days or 0)))
    found: list[HolidayWindow] = []
    for year in (today.year - 1, today.year, today.year + 1):
        span = _core_span(rule, year)
        if span is None:
            continue
        core_start, core_end = span
        window_start = core_start - timedelta(days=lead)
        window_end = core_end + timedelta(days=after)
        if window_start <= today <= window_end:
            found.append(
                HolidayWindow(
                    rule=rule,
                    core_start=core_start,
                    core_end=core_end,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
    return found


def next_core(rule: HolidayRule, today: date) -> Optional[tuple[date, date]]:
    best: Optional[tuple[date, date]] = None
    for year in range(today.year - 1, today.year + 3):
        span = _core_span(rule, year)
        if span is None or span[1] < today:
            continue
        if best is None or span[0] < best[0]:
            best = span
    return best


def resolve_visible_holiday(rules: list[HolidayRule], today: date) -> Optional[VisibleHoliday]:
    hits: list[HolidayWindow] = []
    for rule in rules:
        if not rule.enabled:
            continue
        hits.extend(windows_covering(rule, today))
    if not hits:
        return None
    primary = [item for item in hits if item.core_start <= today <= item.core_end]
    if primary:
        primary.sort(key=lambda item: ((item.core_end - item.core_start).days, item.rule.priority, item.rule.code))
        chosen = primary[0]
    else:
        hits.sort(key=lambda item: (item.rule.priority, -(item.window_end - item.window_start).days, item.rule.code))
        chosen = hits[0]
    if chosen.core_start <= today <= chosen.core_end:
        mode = "active"
        sale_phase = "active" if chosen.rule.sale_percent > 0 else None
    elif today < chosen.core_start:
        mode = "teaser"
        sale_phase = "teaser" if chosen.rule.sale_percent > 0 else None
    else:
        mode = "after"
        sale_phase = None
    return VisibleHoliday(
        code=chosen.rule.code,
        name=chosen.rule.name,
        mode=mode,
        sale_phase=sale_phase,
        sale_percent=chosen.rule.sale_percent,
        sale_label=chosen.rule.sale_label,
        lead_days=chosen.rule.lead_days,
        core_start=chosen.core_start,
        core_end=chosen.core_end,
        window_start=chosen.window_start,
        window_end=chosen.window_end,
    )


def apply_override(rule: HolidayRule, row: object) -> HolidayRule:
    if row is None:
        return rule

    def _int(name: str, fallback: int) -> int:
        value = getattr(row, name, None)
        return fallback if value is None else int(value)

    def _float(name: str, fallback: float) -> float:
        value = getattr(row, name, None)
        return fallback if value is None else float(value)

    updated = replace(
        rule,
        enabled=bool(getattr(row, "enabled", rule.enabled)),
        start_month=_int("start_month", rule.start_month),
        start_day=_int("start_day", rule.start_day),
        end_month=_int("end_month", rule.end_month),
        end_day=_int("end_day", rule.end_day),
        lead_days=_int("lead_days", rule.lead_days),
        after_days=_int("after_days", rule.after_days),
        sale_percent=max(0.0, min(50.0, _float("sale_percent", rule.sale_percent))),
    )
    return updated
