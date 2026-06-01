"""Xác nhận đơn hoàn đã trả shop — nhập mã / import Excel."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import crud
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


def parse_order_codes_from_text(text: str) -> list[dict[str, Any]]:
    """Mỗi dòng / mã cách nhau bởi dấu phẩy, chấm phẩy, xuống dòng."""
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for part in _CODE_SPLIT_RE.split(line.strip()):
            raw = part.strip()
            if not raw:
                continue
            entries.append(
                {
                    "row_number": line_no,
                    "raw": raw,
                    "order_code": normalize_shop_order_code(raw),
                }
            )
    return entries


def parse_order_codes_from_excel(
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
        code: Optional[str] = None
        raw_display = ""
        for cell in row:
            cell_text = _cell_str(cell)
            if not cell_text:
                continue
            candidate = normalize_shop_order_code(cell_text)
            if candidate:
                code = candidate
                raw_display = cell_text.strip()
                break
        if not code:
            joined = " ".join(_cell_str(c) for c in row if _cell_str(c)).strip()
            if not joined:
                continue
            raw_display = joined[:120]
        entries.append(
            {
                "row_number": row_idx,
                "raw": raw_display or f"(dòng {row_idx})",
                "order_code": code,
            }
        )

    if not entries:
        warnings.append("Không có dòng nào trong file (cột mã đơn shop dạng DHxxx).")
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
    entries = parse_order_codes_from_text(text)
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
    entries, warnings = parse_order_codes_from_excel(file_bytes, source_filename=source_filename)
    payload = confirm_shop_returns_from_entries(
        db,
        entries,
        admin_id=admin_id,
        note=note,
        source="excel",
    )
    payload["warnings"] = list(payload.get("warnings") or []) + warnings
    return payload
