"""Đích khi khách bấm một thông báo — trang thao tác, không phải hộp thư."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

_ORDER_CODE_RE = re.compile(r"\b(DH\d+)\b", re.IGNORECASE)
_DEDUPE_RE = re.compile(r"^order:(\d+):([a-z0-9_]+)$")


def clean_action_url(url: Optional[str]) -> Optional[str]:
    """Chỉ nhận đường dẫn nội bộ. Bỏ link ngoài và đường dẫn trống."""
    if not url:
        return None
    value = str(url).strip()
    if not value.startswith("/") or value.startswith("//"):
        return None
    if "\\" in value or any(ch.isspace() for ch in value):
        return None
    if value.rstrip("/") == "/account/notifications":
        return None
    return value[:500]


def order_action_path(title: str, content: str, order_id: int) -> str:
    blob = f"{title}\n{content}".lower()
    if "đánh giá" in blob or "giao hàng thành công" in blob or "giao thành công" in blob:
        return f"/account/orders/{order_id}/review"
    if any(token in blob for token in ("vận chuyển", "vận đơn", "bưu tá", "đang vận chuyển")):
        return f"/account/orders/{order_id}/tracking"
    return f"/account/orders/{order_id}"


def destination_for(notif) -> tuple[Optional[str], Optional[str]]:
    """
    Trả (đường dẫn, mã đơn cần tra).
    Đường dẫn đã đủ thì mã đơn là None. Cần tra đơn thì đường dẫn là None.
    """
    stored = clean_action_url(getattr(notif, "action_url", None))
    if stored:
        return stored, None

    title = getattr(notif, "title", None) or ""
    content = getattr(notif, "content", None) or ""
    blob = f"{title}\n{content}"
    low = blob.lower()
    kind = (getattr(notif, "type", None) or "").strip().lower()

    if "cartsave188" in low or "giỏ" in low:
        return "/cart", None

    if kind == "affiliate" or "hoa hồng" in low or "link giới thiệu" in low:
        return "/vi-dien-tu", None

    dedupe = getattr(notif, "dedupe_key", None) or ""
    match = _DEDUPE_RE.match(dedupe)
    if match:
        order_id, event = match.group(1), match.group(2)
        if event in ("delivered", "order_delivered"):
            return f"/account/orders/{order_id}/review", None
        if event in ("tracking_assigned", "order_shipping") or event.startswith("phase_"):
            return f"/account/orders/{order_id}/tracking", None
        return f"/account/orders/{order_id}", None

    if kind == "promotion" or "khuyến mãi" in low or low.startswith("bạn nhận quà"):
        return "/account/khuyen-mai", None

    found = _ORDER_CODE_RE.search(blob)
    if found:
        return None, found.group(1).upper()
    return None, None


def attach_action_urls(db: Session, notifications: list) -> None:
    """Gắn action_url để API trả đúng trang đích, kể cả thông báo cũ chưa lưu link."""
    pending: list[tuple[object, str]] = []
    codes: set[str] = set()
    resolved: dict[int, str] = {}

    for notif in notifications:
        path, code = destination_for(notif)
        if path:
            resolved[id(notif)] = path
            continue
        if code:
            pending.append((notif, code))
            codes.add(code)

    order_ids: dict[str, int] = {}
    if codes:
        from app.models.order import Order

        rows = (
            db.query(Order.id, Order.order_code)
            .filter(func.upper(Order.order_code).in_(list(codes)))
            .all()
        )
        order_ids = {(row.order_code or "").strip().upper(): int(row.id) for row in rows}

    for notif, code in pending:
        order_id = order_ids.get(code)
        if not order_id:
            continue
        resolved[id(notif)] = order_action_path(
            getattr(notif, "title", None) or "",
            getattr(notif, "content", None) or "",
            order_id,
        )

    for notif in notifications:
        path = resolved.get(id(notif))
        if path and (getattr(notif, "action_url", None) or "") != path:
            notif.action_url = path
