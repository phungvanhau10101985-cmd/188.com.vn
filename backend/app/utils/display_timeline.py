# Thời điểm hiển thị công khai: đánh giá / hỏi đáp import — quy tắc ngày (pseudo-random theo id).
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def to_utc_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def imported_topic_days_ago(entity_id: int) -> int:
    """
    Thời gian chủ đề (câu hỏi / đánh giá) import: cách hôm nay 4–20 ngày, ổn định theo id.
    """
    return 4 + abs(int(entity_id)) % 17


def imported_reply_gap_days(entity_id: int, slot_index: int) -> int:
    """
    Khoảng cách (ngày) giữa lượt trước và lượt kế tiếp: 2–7 ngày, pseudo-random theo id + lượt.
    """
    h = abs(int(entity_id)) * 10007 + int(slot_index) * 1301
    return 2 + (h % 6)


def merge_imported_display_created_at(obj: Any, update: dict, now: datetime) -> None:
    """Bản import: display_created_at = now − (4…20 ngày)."""
    if not getattr(obj, "is_imported", False):
        return
    d = imported_topic_days_ago(int(obj.id))
    update["display_created_at"] = to_utc_aware(now) - timedelta(days=d)


def _synthetic_import_reply_after(
    prev_time: datetime,
    entity_id: int,
    slot_index: int,
    now_utc: datetime,
) -> datetime:
    """
    Timestamp lượt trả lời sau prev_time: +(2…7 ngày); neo về quá khứ nếu vượt hiện tại.
    """
    nu = to_utc_aware(now_utc)
    prv = to_utc_aware(prev_time)
    gap = imported_reply_gap_days(entity_id, slot_index)
    cand = prv + timedelta(days=gap)

    if cand < nu:
        return cand

    tail_days = imported_reply_gap_days(entity_id, slot_index + 100)
    cand = nu - timedelta(days=tail_days)
    if cand <= prv:
        cand = prv + timedelta(days=gap)
    if cand >= nu:
        # 2..7 ngày trước hiện tại (pseudo-random theo id + slot)
        h = abs(int(entity_id)) * 31 + slot_index * 17
        cand = nu - timedelta(days=2 + (h % 6))
    if cand <= prv:
        cand = prv + timedelta(days=2)
    return cand


def reply_display_at(
    reply_at: Optional[datetime],
    question_or_review_shown_at: Optional[datetime],
    entity_id: int,
    seq: int = 0,
) -> Optional[datetime]:
    """Bản không import: chỉnh nhẹ nếu timestamp DB lệch (theo giờ)."""
    floor = to_utc_aware(question_or_review_shown_at)
    if floor is None:
        return reply_at
    ra = to_utc_aware(reply_at)
    if ra is not None and ra > floor:
        return ra
    offset_hours = 1 + (abs(int(entity_id)) + seq * 17) % 72
    return floor + timedelta(hours=offset_hours)


def merge_review_reply_display_times(obj: Any, update: dict, now: datetime) -> None:
    if not (getattr(obj, "reply_content", None) or "").strip():
        return
    shown = update.get("display_created_at") or getattr(obj, "created_at", None)
    if getattr(obj, "is_imported", False):
        sh = to_utc_aware(shown)
        nu = to_utc_aware(now)
        if sh is None:
            return
        update["display_reply_at"] = _synthetic_import_reply_after(sh, int(obj.id), 0, nu)
        return
    update["display_reply_at"] = reply_display_at(
        getattr(obj, "reply_at", None),
        shown,
        int(obj.id),
        1,
    )


def merge_question_reply_display_times(obj: Any, update: dict, now: datetime) -> None:
    """
    - Import: chuỗi trả lời, mỗi bước + (2…7) ngày sau lượt trước.
    - Không import: giữ reply_display_at theo DB / vá lệch nhẹ.
    """
    shown = update.get("display_created_at") or getattr(obj, "created_at", None)
    shown_aware = to_utc_aware(shown)
    if shown_aware is None:
        return

    nu = to_utc_aware(now)
    oid = int(obj.id)

    if getattr(obj, "is_imported", False):
        slot_idx = 0
        prev = shown_aware
        if (getattr(obj, "reply_admin_content", None) or "").strip():
            r = _synthetic_import_reply_after(prev, oid, slot_idx, nu)
            slot_idx += 1
            prev = r
            update["display_reply_admin_at"] = r
        if (getattr(obj, "reply_user_one_content", None) or "").strip():
            r = _synthetic_import_reply_after(prev, oid, slot_idx, nu)
            slot_idx += 1
            prev = r
            update["display_reply_user_one_at"] = r
        if (getattr(obj, "reply_user_two_content", None) or "").strip():
            update["display_reply_user_two_at"] = _synthetic_import_reply_after(prev, oid, slot_idx, nu)
        return

    floor: datetime = shown_aware
    seq = 1

    if (getattr(obj, "reply_admin_content", None) or "").strip():
        d = reply_display_at(getattr(obj, "reply_admin_at", None), floor, oid, seq)
        update["display_reply_admin_at"] = d
        du = to_utc_aware(d)
        if du and du > floor:
            floor = du
        seq += 1

    if (getattr(obj, "reply_user_one_content", None) or "").strip():
        d = reply_display_at(getattr(obj, "reply_user_one_at", None), floor, oid, seq)
        update["display_reply_user_one_at"] = d
        du = to_utc_aware(d)
        if du and du > floor:
            floor = du
        seq += 1

    if (getattr(obj, "reply_user_two_content", None) or "").strip():
        update["display_reply_user_two_at"] = reply_display_at(
            getattr(obj, "reply_user_two_at", None), floor, oid, seq
        )
