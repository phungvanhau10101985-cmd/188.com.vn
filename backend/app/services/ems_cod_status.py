"""Trạng thái COD EMS đã trả shop."""

from __future__ import annotations


def _key(status: str | None) -> str:
    return (status or "").strip().lower()


def is_cod_settlement_paid(status: str | None) -> bool:
    """File đối soát khớp, hoặc shop xác nhận EMS đã trả đủ sau khi lệch."""
    key = _key(status)
    return key in {"matched", "confirmed_full"}


def is_cod_amount_mismatch(status: str | None) -> bool:
    return _key(status) == "amount_mismatch"


def should_preserve_confirmed_full(existing_status: str | None, next_status: str | None) -> bool:
    """Xác nhận trả đủ không bị file đối soát lệch ghi đè. File khớp sau đó thì cho cập nhật."""
    return _key(existing_status) == "confirmed_full" and _key(next_status) != "matched"
