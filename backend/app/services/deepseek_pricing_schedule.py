"""DeepSeek API peak/off-peak pricing windows (UTC, mid-2026 policy).

Peak (2× price): 01:00–04:00 UTC and 06:00–10:00 UTC.
Off-peak: all other hours (17 h/day).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from zoneinfo import ZoneInfo

# Half-open minute ranges [start, end) from midnight UTC.
_DEEPSEEK_PEAK_MINUTE_RANGES_UTC: Tuple[Tuple[int, int], ...] = (
    (60, 240),   # 01:00–04:00
    (360, 600),  # 06:00–10:00
)

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _minute_of_day_utc(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.hour * 60 + dt.minute


def is_deepseek_peak_utc(dt: datetime | None = None) -> bool:
    """True when DeepSeek bills at peak (2×) rate."""
    now = dt or datetime.now(timezone.utc)
    minute = _minute_of_day_utc(now)
    return any(start <= minute < end for start, end in _DEEPSEEK_PEAK_MINUTE_RANGES_UTC)


def is_deepseek_off_peak_utc(dt: datetime | None = None) -> bool:
    return not is_deepseek_peak_utc(dt)


def seconds_until_deepseek_off_peak(dt: datetime | None = None) -> int:
    """Seconds until the current peak window ends; 0 if already off-peak."""
    now = dt or datetime.now(timezone.utc)
    if is_deepseek_off_peak_utc(now):
        return 0
    minute = _minute_of_day_utc(now)
    for start, end in _DEEPSEEK_PEAK_MINUTE_RANGES_UTC:
        if start <= minute < end:
            end_dt = now.astimezone(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(minutes=end)
            return max(0, int((end_dt - now.astimezone(timezone.utc)).total_seconds()))
    return 0


def deepseek_off_peak_hours_per_day() -> int:
    peak_minutes = sum(end - start for start, end in _DEEPSEEK_PEAK_MINUTE_RANGES_UTC)
    return (24 * 60 - peak_minutes) // 60


def deepseek_peak_hours_per_day() -> int:
    return 24 - deepseek_off_peak_hours_per_day()


def _format_vn_time_ranges(ranges: List[Tuple[int, int]]) -> str:
    parts: List[str] = []
    for start, end in ranges:
        sh, sm = divmod(start, 60)
        eh, em = divmod(end, 60)
        parts.append(f"{sh:02d}:{sm:02d}–{eh:02d}:{em:02d}")
    return ", ".join(parts)


def deepseek_pricing_schedule_summary_vn() -> str:
    """Human-readable schedule in Vietnam time (UTC+7)."""
    peak_vn: List[Tuple[int, int]] = []
    for start, end in _DEEPSEEK_PEAK_MINUTE_RANGES_UTC:
        base = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=start)
        end_base = datetime(2000, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=end)
        peak_vn.append(
            (
                base.astimezone(_VN_TZ).hour * 60 + base.astimezone(_VN_TZ).minute,
                end_base.astimezone(_VN_TZ).hour * 60 + end_base.astimezone(_VN_TZ).minute,
            )
        )
    return (
        f"Cao điểm (×2 giá): {_format_vn_time_ranges(peak_vn)} (giờ VN). "
        f"Thấp điểm: {deepseek_off_peak_hours_per_day()} giờ/ngày."
    )


def off_peak_wait_message_vi(seconds_remaining: int) -> str:
    mins = max(1, (seconds_remaining + 59) // 60)
    resume_at = datetime.now(timezone.utc) + timedelta(seconds=seconds_remaining)
    resume_vn = resume_at.astimezone(_VN_TZ).strftime("%H:%M")
    return (
        f"Chờ giờ thấp điểm DeepSeek (giá rẻ) — còn ~{mins} phút, tiếp tục sau ~{resume_vn} (giờ VN). "
        f"{deepseek_pricing_schedule_summary_vn()}"
    )
