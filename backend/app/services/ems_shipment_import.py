from __future__ import annotations

import io
import re
from typing import Any, Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app import crud
from app.models.order import Order, OrderStatus
from app.models.order_shipment import OrderShipmentEvent
from app.services import ems_tracking as ems_tracking_svc

_ORDER_CODE_RE = re.compile(r"\b(DH\d+)\b", re.IGNORECASE)
_COL_REF_NAMES = ("MA_DON_HANG", "MA THAM CHIEU", "MA_THAM_CHIEU")
_COL_RECIPIENT_NAMES = ("TEN_NGUOI_NHAN", "TEN NGUOI NHAN")


def _norm_header(value: Any) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "_", text)


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none"):
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def extract_order_code_from_recipient(text: Optional[str]) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    match = _ORDER_CODE_RE.search(raw)
    return match.group(1).upper() if match else None


def _find_header_map(rows: list[tuple[Any, ...]]) -> tuple[int, dict[str, int]]:
    for idx, row in enumerate(rows[:10]):
        mapping: dict[str, int] = {}
        for col_idx, cell in enumerate(row):
            key = _norm_header(cell)
            if key in _COL_REF_NAMES:
                mapping["reference_code"] = col_idx
            if key in _COL_RECIPIENT_NAMES:
                mapping["recipient_label"] = col_idx
        if "reference_code" in mapping and "recipient_label" in mapping:
            return idx, mapping
    return 0, {"reference_code": 3, "recipient_label": 9}


def parse_ems_export_rows(file_bytes: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        ws = wb.active
        raw_rows = [tuple(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()

    if not raw_rows:
        return [], ["File Excel trống."]

    header_idx, col_map = _find_header_map(raw_rows)
    if header_idx > 0:
        warnings.append(f"Phát hiện dòng tiêu đề ở hàng {header_idx + 1}.")

    ref_col = col_map.get("reference_code", 3)
    recipient_col = col_map.get("recipient_label", 9)
    parsed: list[dict[str, Any]] = []

    for row_idx, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        ref_code = _cell_str(row[ref_col] if ref_col < len(row) else "")
        recipient_label = _cell_str(row[recipient_col] if recipient_col < len(row) else "")
        if not ref_code and not recipient_label:
            continue
        parsed.append(
            {
                "row_number": row_idx,
                "reference_code": ref_code.upper(),
                "recipient_label": recipient_label,
                "order_code": extract_order_code_from_recipient(recipient_label),
            }
        )

    if not parsed:
        warnings.append("Không có dòng dữ liệu hợp lệ (cột D mã tham chiếu / cột J tên người nhận).")
    return parsed, warnings


def _ems_phase(description: Optional[str]) -> str:
    text = (description or "").lower()
    if "phát thành công" in text or "delivered successfully" in text:
        return "delivered"
    if "[cod]trả tiền" in text.replace(" ", ""):
        return "cod_settled"
    if "[cod]đã thu tiền" in text.replace(" ", ""):
        return "cod_collected"
    if "giao bưu tá" in text or "out for delivery" in text:
        return "out_for_delivery"
    if "vận chuyển" in text or "đến bưu cục" in text or "arrival at po" in text:
        return "in_transit"
    if "chấp nhận gửi" in text or "posting / collection" in text:
        return "posted"
    return "unknown"


def _compare_ems_with_order(
    *,
    ems_phase: str,
    order_status: Optional[str],
    current_step_key: Optional[str],
) -> tuple[str, str]:
    st = (order_status or "").strip().lower()
    step = (current_step_key or "").strip().lower()

    if ems_phase in ("delivered", "cod_collected", "cod_settled"):
        if st in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
            return "matched", "EMS đã phát — đơn shop đã giao/hoàn tất."
        if st == OrderStatus.SHIPPING.value or step in ("domestic_shipping", "awaiting_confirm"):
            return "in_progress", "EMS đã phát — đơn shop đang giao/chờ khách xác nhận."
        return "mismatch", "EMS đã phát thành công nhưng đơn shop chưa cập nhật trạng thái giao."

    if ems_phase in ("out_for_delivery", "in_transit", "posted"):
        if st in (OrderStatus.SHIPPING.value, OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
            return "in_progress", "EMS đang vận chuyển/phát — đơn shop đã ở giai đoạn giao."
        if step in ("domestic_shipping", "awaiting_confirm"):
            return "in_progress", "EMS đang vận chuyển — timeline shop đã tới bước giao nội địa."
        return "mismatch", "EMS đang vận chuyển nhưng đơn shop chưa cập nhật giao hàng."

    if st in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
        return "mismatch", "Đơn shop đã giao nhưng EMS chưa báo phát thành công."

    return "in_progress", "Chưa đủ dữ liệu để kết luận — cần kiểm tra thủ công."


def _order_timeline_summary(db: Session, order: Order) -> tuple[Optional[str], Optional[str]]:
    """Đọc timeline hiện tại — không gọi advance_auto_milestones (tránh ghi DB khi import)."""
    st = getattr(order.status, "value", order.status)
    events = (
        db.query(OrderShipmentEvent)
        .filter(OrderShipmentEvent.order_id == order.id)
        .order_by(OrderShipmentEvent.sort_order.asc())
        .all()
    )
    current_key = None
    for ev in events:
        if ev.status == "active":
            current_key = ev.step_key
            break
    return current_key, st


def process_ems_import_row(db: Session, row: dict[str, Any]) -> dict[str, Any]:
    reference_code = (row.get("reference_code") or "").strip().upper()
    order_code = (row.get("order_code") or "").strip().upper() or None
    recipient_label = row.get("recipient_label") or ""

    result: dict[str, Any] = {
        **row,
        "order_id": None,
        "order_status": None,
        "current_step_key": None,
        "tracking_number_saved": None,
        "ems_tracking_code": None,
        "ems_reference_code": None,
        "ems_status": None,
        "ems_phase": None,
        "sync_status": "pending",
        "sync_message": "",
        "ems_error": None,
    }

    if not order_code:
        result["sync_status"] = "parse_error"
        result["sync_message"] = "Không tách được mã đơn (DHxxx) từ cột TEN_NGUOI_NHAN."
        return result

    order = crud.order.get_order_by_code(db, order_code)
    if not order:
        result["sync_status"] = "order_not_found"
        result["sync_message"] = f"Không tìm thấy đơn {order_code} trên 188.com.vn."
    else:
        result["order_id"] = order.id
        result["order_status"] = getattr(order.status, "value", order.status)
        result["tracking_number_saved"] = order.tracking_number
        step_key, _ = _order_timeline_summary(db, order)
        result["current_step_key"] = step_key

    if not reference_code:
        result["sync_status"] = "parse_error"
        result["sync_message"] = "Thiếu mã tham chiếu EMS (cột D / MA_DON_HANG)."
        return result

    ems = ems_tracking_svc.fetch_ems_tracking(reference_code)
    if ems.get("error") and not ems.get("events"):
        result["sync_status"] = "ems_not_found"
        result["ems_error"] = ems.get("error")
        result["sync_message"] = ems.get("error") or "Không tra được EMS."
        return result

    ems_status = ems.get("current_status_description") or ""
    ems_phase = _ems_phase(ems_status)
    result["ems_tracking_code"] = ems.get("tracking_code")
    result["ems_reference_code"] = ems.get("reference_code") or reference_code
    result["ems_status"] = ems_status
    result["ems_phase"] = ems_phase

    if not order:
        return result

    sync_status, sync_message = _compare_ems_with_order(
        ems_phase=ems_phase,
        order_status=result["order_status"],
        current_step_key=result["current_step_key"],
    )
    result["sync_status"] = sync_status
    result["sync_message"] = sync_message

    saved_tracking = (order.tracking_number or "").strip().upper()
    ems_tracking = (result["ems_tracking_code"] or "").strip().upper()
    if ems_tracking and saved_tracking and saved_tracking != ems_tracking:
        result["sync_status"] = "mismatch"
        result["sync_message"] = (
            f"Mã vận đơn shop ({saved_tracking}) khác EMS ({ems_tracking}). "
            + result["sync_message"]
        )

    return result


def import_ems_shipment_excel(db: Session, file_bytes: bytes) -> dict[str, Any]:
    rows, warnings = parse_ems_export_rows(file_bytes)
    results = [process_ems_import_row(db, row) for row in rows]

    summary = {
        "total_rows": len(results),
        "matched": sum(1 for r in results if r["sync_status"] == "matched"),
        "in_progress": sum(1 for r in results if r["sync_status"] == "in_progress"),
        "mismatch": sum(1 for r in results if r["sync_status"] == "mismatch"),
        "order_not_found": sum(1 for r in results if r["sync_status"] == "order_not_found"),
        "ems_not_found": sum(1 for r in results if r["sync_status"] == "ems_not_found"),
        "parse_error": sum(1 for r in results if r["sync_status"] == "parse_error"),
    }

    return {
        "ok": True,
        "warnings": warnings,
        "summary": summary,
        "rows": results,
    }
