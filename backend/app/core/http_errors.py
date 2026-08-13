"""Phân biệt 404 'không khớp route' với 404 nghiệp vụ (HTTPException có detail)."""
from __future__ import annotations

from typing import Any, Optional

_DEFAULT_ROUTE_404 = frozenset({"not found", "not found."})


def business_404_content(exc: Any) -> Optional[dict[str, Any]]:
    """JSON body khi endpoint chủ động 404. None = route không tồn tại (payload debug)."""
    detail = getattr(exc, "detail", None)
    if isinstance(detail, dict):
        return detail
    if isinstance(detail, str):
        text = detail.strip()
        if text and text.lower() not in _DEFAULT_ROUTE_404:
            return {"detail": text}
    return None
