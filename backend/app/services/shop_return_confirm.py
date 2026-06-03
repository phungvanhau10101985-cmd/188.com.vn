"""Xác nhận đơn hoàn đã trả shop — nhập mã DH / mã EMS / mã tham chiếu."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.order import Order, OrderItem
from app.models.order_shipment import EmsShippingRecord
from app.services.ems_excel_utils import read_spreadsheet_rows
from app.services.ems_shipment_import import (
    _cell_str,
    extract_warehouse_sku_from_ems_label,
    looks_like_recipient_not_sku,
    warehouse_sku_from_col_h_cell,
)
from app import crud
from app.services.shipping_operations import (
    _is_ems_return_pending_shop,
    bulk_confirm_shop_returns,
    find_ems_record_by_token,
    order_has_ems_return_marker,
    preview_shop_returns,
)

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


def resolve_shop_return_input(
    db: Session,
    raw: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Trả (order_code shop, lỗi).
    Nhận: DHxxx/DCxxx/H… | mã EMS | mã tham chiếu cột A | mã đơn trên dòng EMS.
    """
    text = (raw or "").strip()
    if not text:
        return None, "Mã trống."

    dh = normalize_shop_order_code(text)
    if dh:
        return dh, None

    record = find_ems_record_by_token(db, text)
    if record:
        order_code = (record.order_code or "").strip().upper()
        if order_code:
            return order_code, None

        if record.order_id:
            order = db.query(Order).filter(Order.id == record.order_id).first()
            if order and order.order_code:
                return order.order_code.strip().upper(), None

        ref = (record.reference_code or text).strip().upper()
        return None, f"Vận đơn EMS {ref} chưa gắn mã đơn shop — kiểm tra import file gửi EMS."

    order = crud.order.get_order_by_code(db, text)
    if order and order.order_code:
        return order.order_code.strip().upper(), None

    return (
        None,
        f"Không tìm thấy «{text[:40]}» trong bảng vận chuyển EMS (mã EMS / tham chiếu / mã đơn H·DC·DH…).",
    )


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


def _warehouse_sku_from_ems_record(record: EmsShippingRecord) -> Optional[str]:
    """Chỉ lấy SKU từ cột H (product_code) — không dùng nhãn người nhận."""
    raw = (getattr(record, "product_code", None) or "").strip()
    if not raw or looks_like_recipient_not_sku(raw):
        return None
    return warehouse_sku_from_col_h_cell(raw)


def _sku_from_order(db: Session, order: Order) -> tuple[Optional[str], str]:
    item = (
        db.query(OrderItem)
        .options(joinedload(OrderItem.product))
        .filter(OrderItem.order_id == order.id)
        .order_by(OrderItem.id.asc())
        .first()
    )
    if item is None or item.product is None:
        return None, ""
    pid = (item.product.product_id or "").strip()
    if not pid:
        return None, ""
    sku = extract_warehouse_sku_from_ems_label(pid) or pid
    return sku, "order_item"


def resolve_warehouse_sku_for_return_intake(db: Session, token: str) -> dict[str, Any]:
    """
    Trích mã kho (cột H file gui ems — trước dấu «-» đầu) từ mã EMS / tham chiếu / DHxxx.
    """
    text = (token or "").strip()
    if not text:
        return {"ok": False, "sku": None, "order_code": None, "source": None, "message": "Mã trống."}

    record = find_ems_record_by_token(db, text)
    order_code: Optional[str] = None

    if record is not None:
        if not _is_ems_return_pending_shop(ems_status=record.ems_status):
            ems_label = (record.ems_status or "").strip() or "—"
            return {
                "ok": False,
                "sku": None,
                "order_code": (record.order_code or "").strip().upper() or None,
                "source": None,
                "message": (
                    f"EMS chưa báo đơn hoàn (trạng thái: «{ems_label}»). "
                    "Chỉ tra mã SKU khi EMS đã phát hoàn / chuyển hoàn."
                ),
            }

        order_code = (record.order_code or "").strip().upper() or None
        if not order_code and record.order_id:
            order = db.query(Order).filter(Order.id == record.order_id).first()
            if order and order.order_code:
                order_code = order.order_code.strip().upper()

        pc = _warehouse_sku_from_ems_record(record)
        if pc:
            return {
                "ok": True,
                "sku": pc,
                "order_code": order_code,
                "source": "ems_column_h",
                "message": None,
            }

        if record.order_id:
            order = db.query(Order).filter(Order.id == record.order_id).first()
            if order:
                sku, src = _sku_from_order(db, order)
                if sku:
                    return {
                        "ok": True,
                        "sku": sku,
                        "order_code": order_code or (order.order_code or "").strip().upper() or None,
                        "source": src,
                        "message": None,
                    }

    dh = normalize_shop_order_code(text)
    if dh:
        order = db.query(Order).filter(Order.order_code.ilike(dh)).first()
        if order:
            if not order_has_ems_return_marker(db, order.id):
                return {
                    "ok": False,
                    "sku": None,
                    "order_code": order.order_code.strip().upper(),
                    "source": None,
                    "message": "EMS chưa báo đơn hoàn — chỉ tra mã SKU khi EMS đã phát hoàn / chuyển hoàn.",
                }
            sku, src = _sku_from_order(db, order)
            if sku:
                return {
                    "ok": True,
                    "sku": sku,
                    "order_code": order.order_code.strip().upper(),
                    "source": src,
                    "message": None,
                }
            return {
                "ok": False,
                "sku": None,
                "order_code": order.order_code.strip().upper(),
                "source": None,
                "message": f"Đơn {dh} không có dòng sản phẩm để trích mã SKU.",
            }

    return {
        "ok": False,
        "sku": None,
        "order_code": order_code,
        "source": None,
        "message": (
            "Không trích được mã SKU từ cột H (MA_SP) — "
            "kiểm tra file gửi EMS có cột H (vd. B7796/41/2-XANH LAM-…) và import lại."
        ),
    }


def preview_shop_returns_from_text(
    db: Session,
    text: str,
) -> dict[str, Any]:
    entries = parse_order_codes_from_text(db, text)
    return preview_shop_returns(db, entries, source="preview_text")


def preview_shop_returns_from_excel(
    db: Session,
    file_bytes: bytes,
    *,
    source_filename: Optional[str] = None,
) -> dict[str, Any]:
    entries, warnings = parse_order_codes_from_excel(
        db,
        file_bytes,
        source_filename=source_filename,
    )
    payload = preview_shop_returns(db, entries, source="preview_excel")
    payload["warnings"] = list(payload.get("warnings") or []) + warnings
    return payload


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
