# Thời điểm hiển thị công khai: trả lời luôn sau câu hỏi/đánh giá (đặc biệt import + display_created_at).
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def imported_display_days_ago(entity_id: int, span: int = 20) -> int:
    """1..span theo id — ổn định giữa các lần gọi API (thay random)."""
    return (abs(int(entity_id)) % span) + 1


def reply_display_at(
    reply_at: Optional[datetime],
    question_or_review_shown_at: Optional[datetime],
    entity_id: int,
    seq: int = 0,
) -> Optional[datetime]:
    """
    Thời điểm trả lời hiển thị: luôn sau thời điểm câu hỏi/đánh giá hiển thị.
    Nếu DB đã có reply_at hợp lý (sau mốc) thì giữ nguyên.
    """
    floor = to_utc_aware(question_or_review_shown_at)
    if floor is None:
        return reply_at
    ra = to_utc_aware(reply_at)
    if ra is not None and ra > floor:
        return ra
    offset_hours = 1 + (abs(int(entity_id)) + seq * 17) % 72
    return floor + timedelta(hours=offset_hours)


def merge_question_reply_display_times(obj: Any, update: dict) -> None:
    """
    Bổ sung display_reply_*_at cho ProductQuestion ORM + dict update đã có display_created_at (tuỳ chọn).
    """
    shown = update.get("display_created_at") or getattr(obj, "created_at", None)
    shown_aware = to_utc_aware(shown)
    if shown_aware is None:
        return

    floor: datetime = shown_aware
    seq = 1

    if (getattr(obj, "reply_admin_content", None) or "").strip():
        d = reply_display_at(getattr(obj, "reply_admin_at", None), floor, int(obj.id), seq)
        update["display_reply_admin_at"] = d
        du = to_utc_aware(d)
        if du and du > floor:
            floor = du
        seq += 1

    if (getattr(obj, "reply_user_one_content", None) or "").strip():
        d = reply_display_at(getattr(obj, "reply_user_one_at", None), floor, int(obj.id), seq)
        update["display_reply_user_one_at"] = d
        du = to_utc_aware(d)
        if du and du > floor:
            floor = du
        seq += 1

    if (getattr(obj, "reply_user_two_content", None) or "").strip():
        update["display_reply_user_two_at"] = reply_display_at(
            getattr(obj, "reply_user_two_at", None), floor, int(obj.id), seq
        )
