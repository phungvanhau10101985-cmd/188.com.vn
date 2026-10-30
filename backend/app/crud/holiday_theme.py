from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.holiday_theme_setting import HolidayThemeSetting
from app.schemas.holiday_theme import HolidayThemeAdminOut, HolidayThemePublicOut
from app.utils.ttl_cache import cache as ttl_cache

HOLIDAY_THEME_PUBLIC_CACHE_KEY = "holiday_theme_v1:public"
ALLOWED_THEMES = {"tet"}
_SINGLETON_ID = 1
_VN_TZ = timezone(timedelta(hours=7))
_SALE_LABELS = {"tet": "Sale Tết"}


class HolidayScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class HolidayProgram:
    armed: bool
    mode: str
    theme: Optional[str]
    sale_phase: Optional[str]
    starts_on: Optional[date]
    ends_on: Optional[date]
    lead_days: int
    after_days: int
    sale_percent: float
    window_start: Optional[date]
    window_end: Optional[date]
    sale_label: str


_RULES_TTL_SECONDS = 30.0
_rules_cache: tuple[float, list] | None = None


def invalidate_public_cache() -> None:
    global _rules_cache
    _rules_cache = None
    ttl_cache.invalidate(HOLIDAY_THEME_PUBLIC_CACHE_KEY)


def normalize_theme(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower()
    if not key or key not in ALLOWED_THEMES:
        return None
    return key


def vn_today() -> date:
    return datetime.now(_VN_TZ).date()


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None
    return None


def _fmt_vi(value: date) -> str:
    return f"{value.day}/{value.month}/{value.year}"


def _sale_label(theme_id: Optional[str]) -> str:
    return _SALE_LABELS.get(theme_id or "", "Sale ngày lễ")


def describe_holiday_program(row: Any, today: date) -> HolidayProgram:
    """Cửa sổ giao diện và sale lễ. Sale chỉ chạy khi đã đủ ngày và % > 0."""
    label = _sale_label("tet")
    if row is None:
        return HolidayProgram(False, "off", None, None, None, None, 0, 0, 0.0, None, None, label)

    armed_id = normalize_theme(getattr(row, "active_theme", None))
    lead = max(0, min(60, int(getattr(row, "lead_days", 0) or 0)))
    after = max(0, min(60, int(getattr(row, "after_days", 0) or 0)))
    try:
        pct = float(row.sale_percent) if getattr(row, "sale_percent", None) is not None else 0.0
    except (TypeError, ValueError):
        pct = 0.0
    pct = max(0.0, min(50.0, pct))
    start = _coerce_date(getattr(row, "starts_on", None))
    end = _coerce_date(getattr(row, "ends_on", None))
    label = _sale_label(armed_id or "tet")

    if not armed_id:
        return HolidayProgram(False, "off", None, None, start, end, lead, after, pct, None, None, label)

    if start is None or end is None or end < start:
        return HolidayProgram(True, "manual", armed_id, None, start, end, lead, after, pct, None, None, label)

    window_start = start - timedelta(days=lead)
    window_end = end + timedelta(days=after)
    if today < window_start:
        mode, theme, sale_phase = "upcoming", None, None
    elif today < start:
        mode, theme = "teaser", armed_id
        sale_phase = "teaser" if pct > 0 else None
    elif today <= end:
        mode, theme = "active", armed_id
        sale_phase = "active" if pct > 0 else None
    elif today <= window_end:
        mode, theme, sale_phase = "after", armed_id, None
    else:
        mode, theme, sale_phase = "ended", None, None

    return HolidayProgram(
        True,
        mode,
        theme,
        sale_phase,
        start,
        end,
        lead,
        after,
        pct,
        window_start,
        window_end,
        label,
    )


def schedule_note(program: HolidayProgram) -> str:
    if program.mode == "off":
        return "Chương trình đang tắt. Bật và đặt ngày kỳ lễ để cửa hàng tự đổi giao diện."
    if program.mode == "manual":
        return (
            "Chưa đủ ngày bắt đầu và ngày kết thúc. Bật là khách thấy giao diện ngay, chưa có sale lễ."
        )
    if program.mode == "upcoming" and program.window_start and program.window_end:
        return (
            f"Sắp tới. Giao diện tự bật từ {_fmt_vi(program.window_start)} "
            f"đến {_fmt_vi(program.window_end)}."
        )
    if program.mode == "teaser" and program.starts_on:
        sale = ""
        if program.sale_phase:
            sale = (
                f" Đang báo sắp giảm {program.sale_percent:g}% từ {_fmt_vi(program.starts_on)}. "
                "Sale trùng ngày-tháng bị ẩn trong khoảng này."
            )
        return f"Đang những ngày trước kỳ lễ. Giao diện đã bật.{sale}"
    if program.mode == "active" and program.ends_on:
        if program.sale_phase:
            sale = (
                f" Đang giảm {program.sale_percent:g}% đến hết {_fmt_vi(program.ends_on)}. "
                "Sale trùng ngày-tháng bị ẩn."
            )
        else:
            sale = " Chưa đặt % sale nên giá không đổi."
        tail = ""
        if program.after_days > 0 and program.window_end:
            tail = f" Giao diện giữ đến {_fmt_vi(program.window_end)}."
        return f"Đang trong kỳ lễ.{sale}{tail}"
    if program.mode == "after" and program.window_end:
        return (
            f"Kỳ lễ đã hết. Giao diện còn đến {_fmt_vi(program.window_end)}. "
            "Sale lễ đã tắt, sale trùng ngày-tháng chạy lại nếu tới lịch."
        )
    if program.ends_on:
        return f"Kỳ lễ đã qua ({_fmt_vi(program.ends_on)}). Đặt ngày mới nếu muốn chạy lại."
    return "Kỳ lễ đã qua. Đặt ngày mới nếu muốn chạy lại."


def get_singleton(db: Session) -> Optional[HolidayThemeSetting]:
    return db.query(HolidayThemeSetting).filter(HolidayThemeSetting.id == _SINGLETON_ID).first()


def row_to_public_out(row: HolidayThemeSetting, today: Optional[date] = None) -> HolidayThemePublicOut:
    del row
    return public_theme_out(today)


def public_theme_out(today: Optional[date] = None, db: Optional[Session] = None) -> HolidayThemePublicOut:
    from app.services.holiday_schedule import next_core, resolve_visible_holiday

    current = today or vn_today()
    rules = merged_rules(db)
    visible = resolve_visible_holiday(rules, current)
    years: dict[str, int] = {}
    for rule in rules:
        span = next_core(rule, current)
        if span is not None:
            years[rule.code] = span[0].year
    return HolidayThemePublicOut(
        active_theme=visible.code if visible else None,
        event_year=visible.core_start.year if visible else None,
        event_year_end=visible.core_end.year if visible else None,
        occasion_years=years,
    )


def row_to_admin_out(row: HolidayThemeSetting, today: Optional[date] = None) -> HolidayThemeAdminOut:
    del row, today
    raise HolidayScheduleError("Dùng admin_theme_out")


def get_or_create_singleton(db: Session) -> HolidayThemeSetting:
    row = get_singleton(db)
    if row:
        return row
    row = HolidayThemeSetting(id=_SINGLETON_ID, active_theme=None, lead_days=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_singleton(db: Session, data: Any) -> HolidayThemeAdminOut:
    row = get_or_create_singleton(db)
    payload = data.model_dump(exclude_unset=True)
    if "active_theme" in payload:
        row.active_theme = normalize_theme(payload["active_theme"])
    if payload.get("clear_dates"):
        row.starts_on = None
        row.ends_on = None
    else:
        if "starts_on" in payload:
            row.starts_on = _coerce_date(payload.get("starts_on"))
        if "ends_on" in payload:
            row.ends_on = _coerce_date(payload.get("ends_on"))
    if payload.get("lead_days") is not None:
        row.lead_days = int(payload["lead_days"])
    if payload.get("after_days") is not None:
        row.after_days = int(payload["after_days"])
    if "sale_percent" in payload:
        row.sale_percent = payload.get("sale_percent")

    start = _coerce_date(row.starts_on)
    end = _coerce_date(row.ends_on)
    if (start is None) != (end is None):
        raise HolidayScheduleError("Cần cả ngày bắt đầu và ngày kết thúc kỳ lễ, hoặc để trống cả hai.")
    if start is not None and end is not None and end < start:
        raise HolidayScheduleError("Ngày kết thúc phải sau hoặc trùng ngày bắt đầu.")

    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_public_cache()
    return admin_theme_out(db)


def _fmt_span(start: date, end: date) -> str:
    if start == end:
        return f"{start.day}/{start.month}/{start.year}"
    return f"{start.day}/{start.month}/{start.year} – {end.day}/{end.month}/{end.year}"


def ensure_occasion_rows(db: Session) -> None:
    from app.models.holiday_occasion_setting import HolidayOccasionSetting
    from app.services.holiday_schedule import CATALOG

    existing = {row.code for row in db.query(HolidayOccasionSetting.code).all()}
    missing = [code for code in CATALOG if code not in existing]
    if not missing:
        return
    for code in missing:
        rule = CATALOG[code]
        db.add(
            HolidayOccasionSetting(
                code=code,
                enabled=rule.enabled,
                start_month=rule.start_month,
                start_day=rule.start_day,
                end_month=rule.end_month,
                end_day=rule.end_day,
                lead_days=rule.lead_days,
                after_days=rule.after_days,
                sale_percent=rule.sale_percent,
            )
        )
    db.commit()


def merged_rules(db: Optional[Session]):
    from app.services.holiday_schedule import CATALOG, apply_override

    if db is None:
        return list(CATALOG.values())
    global _rules_cache
    now = time.monotonic()
    if _rules_cache is not None and now - _rules_cache[0] < _RULES_TTL_SECONDS:
        return _rules_cache[1]
    try:
        ensure_occasion_rows(db)
        from app.models.holiday_occasion_setting import HolidayOccasionSetting

        rows = {row.code: row for row in db.query(HolidayOccasionSetting).all()}
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return list(CATALOG.values())
    rules = [apply_override(rule, rows.get(code)) for code, rule in CATALOG.items()]
    _rules_cache = (now, rules)
    return rules


def admin_theme_out(db: Session, today: Optional[date] = None):
    from app.schemas.holiday_theme import HolidayOccasionOut, HolidayThemeAdminOut
    from app.services.holiday_schedule import next_core, resolve_visible_holiday

    current = today or vn_today()
    rules = merged_rules(db)
    visible = resolve_visible_holiday(rules, current)
    occasions = []
    for rule in rules:
        span = next_core(rule, current)
        solar_label = f"Năm {span[0].year}" if span else "Chưa tính được năm"
        if span and span[0].year != span[1].year:
            solar_label = f"Năm {span[0].year}–{span[1].year}"
        occasions.append(
            HolidayOccasionOut(
                code=rule.code,
                name=rule.name,
                calendar=rule.calendar,
                calendar_label="Âm lịch" if rule.calendar == "lunar" else "Dương lịch",
                tagline=rule.tagline,
                summary=rule.summary,
                start_month=rule.start_month,
                start_day=rule.start_day,
                end_month=rule.end_month,
                end_day=rule.end_day,
                lead_days=rule.lead_days,
                after_days=rule.after_days,
                sale_percent=rule.sale_percent,
                enabled=rule.enabled,
                priority=rule.priority,
                solar_label=solar_label,
                start_year=span[0].year if span else None,
                end_year=span[1].year if span else None,
                showing_today=bool(visible and visible.code == rule.code),
            )
        )
    if visible is None:
        note = "Hôm nay cửa hàng dùng giao diện thường. Mốc lễ chỉ lưu ngày và tháng, tự lặp mỗi năm."
    elif visible.mode == "active":
        note = f"Hôm nay khách thấy {visible.name}. Đúng ngày lễ nên giao diện dịp này phủ lên dịp lớn hơn nếu hai kỳ trùng."
    elif visible.mode == "teaser":
        note = f"Hôm nay khách thấy {visible.name}. Đang những ngày trước lễ, báo sắp giảm giá."
    else:
        note = f"Hôm nay khách thấy {visible.name}. Đang giữ giao diện sau lễ, sale lễ đã tắt."
    return HolidayThemeAdminOut(
        active_theme=visible.code if visible else None,
        active_label=visible.name if visible else None,
        schedule_note=note,
        occasions=occasions,
    )


def update_occasion(db: Session, data) -> object:
    from app.models.holiday_occasion_setting import HolidayOccasionSetting
    from app.services.holiday_schedule import CATALOG, valid_month_day

    ensure_occasion_rows(db)
    rule = CATALOG[data.code]
    row = db.query(HolidayOccasionSetting).filter(HolidayOccasionSetting.code == data.code).first()
    if row is None:
        raise HolidayScheduleError("Không thấy dịp lễ")
    payload = data.model_dump(exclude_unset=True)
    for key in ("enabled", "start_month", "start_day", "end_month", "end_day", "lead_days", "after_days", "sale_percent"):
        if key in payload and payload[key] is not None:
            setattr(row, key, payload[key])
    if not valid_month_day(rule.calendar, int(row.start_month), int(row.start_day)):
        raise HolidayScheduleError("Ngày bắt đầu không hợp lệ với loại lịch của dịp này")
    if not valid_month_day(rule.calendar, int(row.end_month), int(row.end_day)):
        raise HolidayScheduleError("Ngày kết thúc không hợp lệ với loại lịch của dịp này")
    db.add(row)
    db.commit()
    invalidate_public_cache()
    return admin_theme_out(db)
