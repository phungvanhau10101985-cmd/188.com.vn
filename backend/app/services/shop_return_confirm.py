"""Xác nhận đơn hoàn đã trả shop — nhập mã DH / mã EMS / mã tham chiếu."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_shipment import EmsShippingRecord
from app.services.ems_excel_utils import read_spreadsheet_rows
from app.services.ems_shipment_import import _cell_str
from app.services.shipping_operations import bulk_confirm_shop_returns

_ORDER_CODE_FULL_RE = re.compile(r"^DH\d+$", re.IGNORECASE)
_ORDER_CODE_SEARCH_RE = re.compile(r"\b(DH\d+)\b", re.IGNORECASE)
_CODE_SPLIT_RE = re.compile(r"[\s,;|\t]+")


def normalize_shop_order_code(raw: str) -> Optional[str]:
    text = (raw or "").strip().upper()
    if not text:
        return None
    if _ORDER_CODE_FULL_RE.match(text):
        return text
    match = _ORDER_CODE_SEARCH_RE.search(text)
    return match.group(1).upper() if match else None


def _find_ems_record_by_token(db: Session, token: str) -> Optional[EmsShippingRecord]:
    """Tra mã vận chuyển EMS, mã tham chiếu (cột A file gửi EMS) hoặc ems_reference_code."""
    t = (token or "").strip().upper()
    if not t or len(t) < 3:
        return None
    for column in (
        EmsShippingRecord.ems_tracking_code,
        EmsShippingRecord.reference_code,
        EmsShippingRecord.ems_reference_code,
    ):
        record = db.query(EmsShippingRecord).filter(column.ilike(t)).first()
        if record:
            return record
    return None


def resolve_shop_return_input(
    db: Session,
    raw: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Trả (order_code DHxxx, lỗi).
    Nhận: DHxxx | mã EMS (tracking) | mã tham chiếu (reference_code).
    """
    text = (raw or "").strip()
    if not text:
        return None, "Mã trống."

    dh = normalize_shop_order_code(text)
    if dh:
        return dh, None

    record = _find_ems_record_by_token(db, text)
    if not record:
        return (
            None,
            f"Không tìm thấy «{text[:40]}» trong bảng vận chuyển EMS (mã EMS / mã tham chiếu).",
        )

    order_code = (record.order_code or "").strip().upper()
    if order_code:
        return order_code, None

    if record.order_id:
        order = db.query(Order).filter(Order.id == record.order_id).first()
        if order and order.order_code:
            return order.order_code.strip().upper(), None

    ref = (record.reference_code or text).strip().upper()
    return None, f"Vận đơn EMS {ref} chưa gắn mã đơn shop (DHxxx) — kiểm tra import file gửi EMS."


def _entry_from_raw(db: Session, *, row_number: int, raw: str) -> dict[str, Any]:
    order_code, resolve_error = resolve_shop_return_input(db, raw)
    return {
        "row_number": row_number,
        "raw": raw,
        "order_code": order_code,
        "resolve_error": resolve_error,
    }


def parse_order_codes_from_text(db: Session, text: str) -> list[dict[str, Any]]:
    """Mỗi dòng / mã cách nhau bởi dấu phẩy, chấm phẩy, xuống dòng."""
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for part in _CODE_SPLIT_RE.split(line.strip()):
            raw = part.strip()
            if not raw:
                continue
            entries.append(_entry_from_raw(db, row_number=line_no, raw=raw))
    return entries


def _resolve_cell_to_entry(db: Session, *, row_idx: int, cell_text: str) -> Optional[dict[str, Any]]:
    text = cell_text.strip()
    if not text:
        return None
    order_code, resolve_error = resolve_shop_return_input(db, text)
    if order_code or resolve_error:
        return {
            "row_number": row_idx,
            "raw": text,
            "order_code": order_code,
            "resolve_error": resolve_error,
        }
    return None


def parse_order_codes_from_excel(
    db: Session,
    file_bytes: bytes,
    *,
    source_filename: Optional[str] = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    raw_rows = read_spreadsheet_rows(file_bytes, source_filename or "")
    if not raw_rows:
        return [], ["File Excel trống."]

    entries: list[dict[str, Any]] = []
    for row_idx, row in enumerate(raw_rows, start=1):
        if not row:
            continue
        matched: Optional[dict[str, Any]] = None
        for cell in row:
            cell_text = _cell_str(cell)
            if not cell_text:
                continue
            candidate = _resolve_cell_to_entry(db, row_idx=row_idx, cell_text=cell_text)
            if candidate:
                matched = candidate
                break
        if matched:
            entries.append(matched)
            continue
        joined = " ".join(_cell_str(c) for c in row if _cell_str(c)).strip()
        if not joined:
            continue
        entries.append(
            _entry_from_raw(db, row_number=row_idx, raw=joined[:120]),
        )

    if not entries:
        warnings.append(
            "Không có dòng hợp lệ (cột mã đơn DHxxx, mã EMS hoặc mã tham chiếu vận đơn)."
        )
    return entries, warnings


def confirm_shop_returns_from_entries(
    db: Session,
    entries: list[dict[str, Any]],
    *,
    admin_id: int,
    note: Optional[str] = None,
    source: str = "manual",
) -> dict[str, Any]:
    return bulk_confirm_shop_returns(
        db,
        entries,
        admin_id=admin_id,
        note=note,
        source=source,
    )


def confirm_shop_returns_from_text(
    db: Session,
    text: str,
    *,
    admin_id: int,
    note: Optional[str] = None,
) -> dict[str, Any]:
    entries = parse_order_codes_from_text(db, text)
    return confirm_shop_returns_from_entries(
        db,
        entries,
        admin_id=admin_id,
        note=note,
        source="manual_text",
    )


def confirm_shop_returns_from_excel(
    db: Session,
    file_bytes: bytes,
    *,
    admin_id: int,
    note: Optional[str] = None,
    source_filename: Optional[str] = None,
) -> dict[str, Any]:
    entries, warnings = parse_order_codes_from_excel(
        db,
        file_bytes,
        source_filename=source_filename,
    )
    payload = confirm_shop_returns_from_entries(
        db,
        entries,
        admin_id=admin_id,
        note=note,
        source="excel",
    )
    payload["warnings"] = list(payload.get("warnings") or []) + warnings
    return payload
