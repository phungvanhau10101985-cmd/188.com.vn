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


def merge_imported_display_created_at(obj: Any, update: dict, now: datetime) -> None:
    """
    Import (đánh giá / hỏi đáp): thời gian hiển thị chủ đề = now − imported_display_days_ago(id).
    """
    if not getattr(obj, "is_imported", False):
        return
    update["display_created_at"] = now - timedelta(days=imported_display_days_ago(int(obj.id)))


def reply_display_at(
    reply_at: Optional[datetime],
    question_or_review_shown_at: Optional[datetime],
    entity_id: int,
    seq: int = 0,
) -> Optional[datetime]:
    """
    Thời điểm trả lời hiển thị: luôn sau thời điểm đánh giá / câu hỏi hiển thị.
    Nếu DB đã có timestamp hợp lý (sau mốc) thì giữ nguyên.
    """
    floor = to_utc_aware(question_or_review_shown_at)
    if floor is None:
        return reply_at
    ra = to_utc_aware(reply_at)
    if ra is not None and ra > floor:
        return ra
    offset_hours = 1 + (abs(int(entity_id)) + seq * 17) % 72
    return floor + timedelta(hours=offset_hours)


def merge_review_reply_display_times(obj: Any, update: dict) -> None:
    """
    Một luồng phản hồi (shop trả đánh giá): seq=1 — cùng công thức như admin trả lời trong Hỏi đáp.
    """
    if not (getattr(obj, "reply_content", None) or "").strip():
        return
    shown = update.get("display_created_at") or getattr(obj, "created_at", None)
    update["display_reply_at"] = reply_display_at(
        getattr(obj, "reply_at", None),
        shown,
        int(obj.id),
        1,
    )


def merge_question_reply_display_times(obj: Any, update: dict) -> None:
    """
    Nhiều lượt trả lời (admin → user1 → user2); mỗi lượt cùng công thức reply_display_at, seq lần lượt.
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
