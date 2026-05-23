from __future__ import annotations

import io
import re
import unicodedata
from typing import Any, Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app import crud
from app.models.order import Order, OrderStatus
from app.models.order_shipment import EmsShippingRecord, OrderShipmentEvent
from app.services import ems_tracking as ems_tracking_svc
from app.services import order_shipment_timeline as shipment_svc

_ORDER_CODE_RE = re.compile(r"\b(DH\d+)\b", re.IGNORECASE)
_DC_CODE_RE = re.compile(r"\b(DC\d+)\b", re.IGNORECASE)
_MADONHANG_RE = re.compile(r"madonhang\s*(DH\d+|DC\d+)", re.IGNORECASE)
_INVALID_ORDER_PLACEHOLDERS = frozenset({
    "ZALO", "XALO", "FACEBOOK", "FB", "SHOPEE", "TIKTOK", "MDH", "NONE", "N/A", "NA",
})

# file gui ems.xlsx (shop export)
_SHOP_EXPORT_HEADERS: dict[str, tuple[str, ...]] = {
    "reference_code": ("MA_VAN_DON",),
    "product_name": ("TEN_SP",),
    "weight": ("TRONG_LUONG",),
    "customer_name": ("TEN_KH",),
    "address": ("DIA_CHI_KH",),
    "phone": ("SDT_KH", "SDT"),
    "cod_amount": ("COD",),
    "product_code": ("MA_SP",),
    "order_code": ("DON_HANG",),
}
_SHOP_EXPORT_DEFAULTS: dict[str, int] = {
    "reference_code": 0,
    "product_name": 1,
    "weight": 2,
    "customer_name": 3,
    "address": 4,
    "phone": 5,
    "cod_amount": 6,
    "product_code": 7,
    "order_code": 8,
}

# EMS export cũ (MA_DON_HANG / TEN_NGUOI_NHAN / TONG_TIEN_THU_HO)
_COL_REF_NAMES = ("MA_DON_HANG", "MA THAM CHIEU", "MA_THAM_CHIEU")
_COL_RECIPIENT_NAMES = ("TEN_NGUOI_NHAN", "TEN NGUOI NHAN")
_COL_COD_NAMES = (
    "TONG_TIEN_THU_HO",
    "TONG TIEN THU HO",
    "TIEN_THU_HO",
    "TIEN THU HO",
    "THU_HO",
)
_EMS_EXPORT_DEFAULTS: dict[str, int] = {
    "reference_code": 3,
    "recipient_label": 9,
    "cod_amount": 15,
}


def _norm_header(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.upper()
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


def _is_placeholder_order_code(code: str) -> bool:
    text = (code or "").strip().upper()
    if not text:
        return True
    if text in _INVALID_ORDER_PLACEHOLDERS:
        return True
    if text.startswith("FB+") or text.endswith("MDH"):
        return True
    return False


def _normalize_external_order_code(code: str) -> Optional[str]:
    text = (code or "").strip().upper()
    if not text or _is_placeholder_order_code(text):
        return None
    if _ORDER_CODE_RE.fullmatch(text) or _DC_CODE_RE.fullmatch(text):
        return text
    dh = _ORDER_CODE_RE.search(text)
    if dh:
        return dh.group(1).upper()
    dc = _DC_CODE_RE.search(text)
    if dc:
        return dc.group(1).upper()
    return None


def extract_order_code_from_recipient(text: Optional[str]) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    madonhang = _MADONHANG_RE.search(raw)
    if madonhang:
        return madonhang.group(1).upper()
    match = _ORDER_CODE_RE.search(raw)
    if match:
        return match.group(1).upper()
    dc = _DC_CODE_RE.search(raw)
    return dc.group(1).upper() if dc else None


def _resolve_order_code(*, direct: Any = None, product_code: Any = None, recipient_label: Any = None) -> Optional[str]:
    direct_code = _normalize_external_order_code(_cell_str(direct))
    if direct_code:
        return direct_code
    for source in (product_code, recipient_label):
        parsed = extract_order_code_from_recipient(_cell_str(source))
        if parsed:
            return parsed
    return None


def _is_shop_order_code(order_code: Optional[str]) -> bool:
    code = (order_code or "").strip().upper()
    return bool(code and _ORDER_CODE_RE.fullmatch(code))


def _build_recipient_label(*, customer_name: str = "", phone: str = "", address: str = "", legacy: str = "") -> str:
    if legacy.strip():
        return legacy.strip()
    parts = [customer_name.strip(), phone.strip()]
    label = " · ".join(p for p in parts if p)
    if address.strip():
        return f"{label} — {address.strip()}" if label else address.strip()
    return label


def _parse_cod_amount(value: Any) -> Optional[int]:
    """Parse cột P TONG_TIEN_THU_HO — tổng tiền thu hộ (VND)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        amt = float(value)
        if amt <= 0:
            return None
        return int(round(amt))
    text = _cell_str(value)
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.-]", "", text)
    if not cleaned:
        return None
    if cleaned.count(".") > 1 and "," not in cleaned:
        cleaned = cleaned.replace(".", "")
    elif cleaned.count(",") > 1 and "." not in cleaned:
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        amt = float(cleaned)
    except ValueError:
        return None
    if amt <= 0:
        return None
    return int(round(amt))


def _match_header_field(key: str, aliases: tuple[str, ...]) -> bool:
    return key in aliases


def _find_header_map(rows: list[tuple[Any, ...]]) -> tuple[int, str, dict[str, int]]:
    for idx, row in enumerate(rows[:10]):
        shop_map: dict[str, int] = {}
        ems_map: dict[str, int] = {}
        for col_idx, cell in enumerate(row):
            key = _norm_header(cell)
            for field, aliases in _SHOP_EXPORT_HEADERS.items():
                if _match_header_field(key, aliases):
                    shop_map[field] = col_idx
            if _match_header_field(key, _COL_REF_NAMES):
                ems_map["reference_code"] = col_idx
            if _match_header_field(key, _COL_RECIPIENT_NAMES):
                ems_map["recipient_label"] = col_idx
            if _match_header_field(key, _COL_COD_NAMES):
                ems_map["cod_amount"] = col_idx

        if shop_map.get("reference_code") is not None and shop_map.get("order_code") is not None:
            merged = {**_SHOP_EXPORT_DEFAULTS, **shop_map}
            return idx, "shop_export", merged
        if ems_map.get("reference_code") is not None and ems_map.get("recipient_label") is not None:
            merged = {**_EMS_EXPORT_DEFAULTS, **ems_map}
            return idx, "ems_export", merged

    return 0, "shop_export", dict(_SHOP_EXPORT_DEFAULTS)


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

    header_idx, file_format, col_map = _find_header_map(raw_rows)
    if header_idx > 0:
        warnings.append(f"Phát hiện dòng tiêu đề ở hàng {header_idx + 1}.")
    if file_format == "shop_export":
        warnings.append(
            "Định dạng file gửi EMS: cột A mã vận đơn, I đơn hàng, G COD, D tên khách."
        )

    ref_col = col_map["reference_code"]
    cod_col = col_map.get("cod_amount", 6 if file_format == "shop_export" else 15)
    parsed: list[dict[str, Any]] = []

    for row_idx, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        ref_code = _cell_str(row[ref_col] if ref_col < len(row) else "").upper()
        cod_raw = row[cod_col] if cod_col < len(row) else None
        cod_amount = _parse_cod_amount(cod_raw)

        if file_format == "shop_export":
            customer_name = _cell_str(row[col_map.get("customer_name", 3)] if col_map.get("customer_name", 3) < len(row) else "")
            phone = _cell_str(row[col_map.get("phone", 5)] if col_map.get("phone", 5) < len(row) else "")
            address = _cell_str(row[col_map.get("address", 4)] if col_map.get("address", 4) < len(row) else "")
            product_code = _cell_str(row[col_map.get("product_code", 7)] if col_map.get("product_code", 7) < len(row) else "")
            order_direct = row[col_map.get("order_code", 8)] if col_map.get("order_code", 8) < len(row) else None
            recipient_label = _build_recipient_label(
                customer_name=customer_name,
                phone=phone,
                address=address,
            )
            order_code = _resolve_order_code(
                direct=order_direct,
                product_code=product_code,
                recipient_label=recipient_label,
            )
        else:
            recipient_col = col_map.get("recipient_label", 9)
            recipient_label = _cell_str(row[recipient_col] if recipient_col < len(row) else "")
            order_code = _resolve_order_code(recipient_label=recipient_label)

        if not ref_code and not recipient_label and not order_code:
            continue
        parsed.append(
            {
                "row_number": row_idx,
                "reference_code": ref_code,
                "recipient_label": recipient_label,
                "order_code": order_code,
                "cod_amount": cod_amount,
            }
        )

    if not parsed:
        if file_format == "shop_export":
            warnings.append(
                "Không có dòng dữ liệu hợp lệ (cột A mã vận đơn / cột I đơn hàng / cột G COD)."
            )
        else:
            warnings.append(
                "Không có dòng dữ liệu hợp lệ (cột MA_DON_HANG mã tham chiếu / TEN_NGUOI_NHAN)."
            )
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


def _ems_only_status_message(ems_phase: str, ems_status: str) -> str:
    """Mô tả trạng thái EMS khi không có / không khớp đơn shop."""
    status = (ems_status or "").strip()
    if ems_phase in ("delivered", "cod_collected", "cod_settled"):
        return status or "EMS đã phát thành công."
    if ems_phase in ("out_for_delivery", "in_transit", "posted"):
        return status or "EMS đang vận chuyển."
    if status:
        return status
    return "EMS chưa có cập nhật hành trình rõ ràng."


def _order_not_found_message(*, order_code: Optional[str], ems_phase: str, ems_status: str) -> str:
    code = (order_code or "").strip().upper()
    ems_part = _ems_only_status_message(ems_phase, ems_status)
    if code and _is_shop_order_code(code):
        return (
            f"Đã lưu vận đơn — chưa có đơn shop {code} trên hệ thống. "
            f"Dùng cho đối soát COD/cước. {ems_part}"
        )
    if code and _DC_CODE_RE.fullmatch(code):
        return (
            f"Đã lưu vận đơn — mã tham chiếu {code} (Deal/CRM, không phải đơn 188.com.vn). "
            f"Dùng cho đối soát COD/cước. {ems_part}"
        )
    if code:
        return (
            f"Đã lưu vận đơn — mã cột I «{code}» không phải đơn shop hợp lệ. "
            f"Dùng cho đối soát COD/cước. {ems_part}"
        )
    return (
        f"Đã lưu vận đơn — thiếu mã đơn ở cột I (DHxxx/DCxxx). "
        f"Dùng cho đối soát COD/cước. {ems_part}"
    )


def _apply_unlinked_result(
    result: dict[str, Any],
    *,
    order_code: Optional[str],
    ems_phase: str = "unknown",
    ems_status: str = "",
    ems_error: Optional[str] = None,
) -> dict[str, Any]:
    """Import thành công nhưng chưa ghép được đơn shop — vẫn lưu COD/EMS để đối soát sau."""
    result["sync_status"] = "unlinked"
    result["sync_message"] = _order_not_found_message(
        order_code=order_code,
        ems_phase=ems_phase,
        ems_status=ems_status if not ems_error else "",
    )
    if ems_error:
        result["ems_error"] = ems_error
    return result


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


def _dedupe_rows_by_reference(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """Gộp dòng trùng mã tham chiếu trong cùng file — giữ dòng cuối."""
    warnings: list[str] = []
    by_ref: dict[str, dict[str, Any]] = {}
    no_ref: list[dict[str, Any]] = []
    dup_count = 0

    for row in rows:
        ref = (row.get("reference_code") or "").strip().upper()
        if not ref:
            no_ref.append(row)
            continue
        if ref in by_ref:
            dup_count += 1
        by_ref[ref] = {**row, "reference_code": ref}

    if dup_count:
        warnings.append(
            f"Có {dup_count} dòng trùng mã tham chiếu trong file — cập nhật theo dòng cuối cùng."
        )

    deduped = no_ref + sorted(by_ref.values(), key=lambda r: r.get("row_number", 0))
    return deduped, warnings


def _ems_lookup_candidates(reference_code: str, order: Optional[Order]) -> list[str]:
    candidates: list[str] = []
    ref = (reference_code or "").strip().upper()
    if ref:
        candidates.append(ref)
    if order:
        saved = (order.tracking_number or "").strip().upper()
        if saved and saved not in candidates:
            candidates.append(saved)
    return candidates


def _fetch_ems_with_fallback(codes: list[str]) -> dict[str, Any]:
    last: dict[str, Any] = {"available": False, "error": "Thiếu mã vận đơn EMS."}
    for code in codes:
        payload = ems_tracking_svc.fetch_ems_tracking(code)
        last = payload
        if payload.get("events") or not payload.get("error"):
            return payload
    return last


def process_ems_import_row(
    db: Session,
    row: dict[str, Any],
    *,
    admin_id: Optional[int] = None,
    skip_ems_tracking: bool = False,
) -> dict[str, Any]:
    reference_code = (row.get("reference_code") or "").strip().upper()
    order_code = (row.get("order_code") or "").strip().upper() or None

    result: dict[str, Any] = {
        **row,
        "reference_code": reference_code,
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
        "order_synced": False,
        "order_sync_message": "",
        "cod_amount": row.get("cod_amount"),
    }

    if not reference_code:
        result["sync_status"] = "parse_error"
        result["sync_message"] = "Thiếu mã vận đơn (cột A / MA_DON_HANG)."
        return result

    order = (
        crud.order.get_order_by_code(db, order_code)
        if _is_shop_order_code(order_code)
        else None
    )

    if skip_ems_tracking:
        result["ems_reference_code"] = reference_code
        if order:
            result["order_id"] = order.id
            result["order_status"] = getattr(order.status, "value", order.status)
            result["tracking_number_saved"] = order.tracking_number
            step_key, _ = _order_timeline_summary(db, order)
            result["current_step_key"] = step_key
            result["sync_status"] = "in_progress"
            result["sync_message"] = (
                f"Đã lưu — ghép đơn {order_code}. Chưa tra EMS (import nhanh file lớn)."
            )
            return result
        return _apply_unlinked_result(
            result,
            order_code=order_code,
            ems_phase="unknown",
            ems_status="",
        )

    ems = _fetch_ems_with_fallback(_ems_lookup_candidates(reference_code, order))
    has_ems = not (ems.get("error") and not ems.get("events"))

    if has_ems:
        ems_status = ems.get("current_status_description") or ""
        ems_phase = _ems_phase(ems_status)
        result["ems_tracking_code"] = ems.get("tracking_code")
        result["ems_reference_code"] = ems.get("reference_code") or reference_code
        result["ems_status"] = ems_status
        result["ems_phase"] = ems_phase
    else:
        ems_status = ""
        ems_phase = "unknown"
        result["ems_error"] = ems.get("error")
        result["ems_reference_code"] = reference_code

    if not order:
        return _apply_unlinked_result(
            result,
            order_code=order_code,
            ems_phase=ems_phase,
            ems_status=ems_status,
            ems_error=result.get("ems_error"),
        )

    result["order_id"] = order.id
    result["order_status"] = getattr(order.status, "value", order.status)
    result["tracking_number_saved"] = order.tracking_number
    step_key, _ = _order_timeline_summary(db, order)
    result["current_step_key"] = step_key

    if not has_ems:
        result["sync_status"] = "in_progress"
        result["sync_message"] = (
            f"Đã ghép đơn {order_code} — chưa tra được hành trình EMS cho mã {reference_code}."
        )
        return result

    if ems_phase != "unknown":
        synced, sync_msg = shipment_svc.apply_ems_import_shipping_sync(
            db,
            order,
            admin_id,
            ems_phase=ems_phase,
            ems_tracking_code=result.get("ems_tracking_code"),
            ems_status_description=ems_status,
        )
        result["order_synced"] = synced
        result["order_sync_message"] = sync_msg
        if synced:
            db.refresh(order)
            result["order_status"] = getattr(order.status, "value", order.status)
            result["tracking_number_saved"] = order.tracking_number
            step_key, _ = _order_timeline_summary(db, order)
            result["current_step_key"] = step_key

    sync_status, sync_message = _compare_ems_with_order(
        ems_phase=ems_phase,
        order_status=result["order_status"],
        current_step_key=result["current_step_key"],
    )
    result["sync_status"] = sync_status
    result["sync_message"] = sync_message
    if result.get("order_sync_message"):
        if result.get("order_synced"):
            result["sync_message"] = f"{result['order_sync_message']} {sync_message}".strip()
        elif result.get("order_id"):
            result["sync_message"] = f"{result['order_sync_message']} ({sync_message})".strip()

    saved_tracking = (order.tracking_number or "").strip().upper()
    ems_tracking = (result["ems_tracking_code"] or "").strip().upper()
    if ems_tracking and saved_tracking and saved_tracking != ems_tracking:
        result["sync_status"] = "mismatch"
        result["sync_message"] = (
            f"Mã vận đơn shop ({saved_tracking}) khác EMS ({ems_tracking}). "
            + result["sync_message"]
        )

    return result


_SYNC_STATUS_ORDER = (
    "matched",
    "in_progress",
    "mismatch",
    "unlinked",
    "order_not_found",
    "ems_not_found",
    "parse_error",
    "pending",
)


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {k: 0 for k in _SYNC_STATUS_ORDER}
    cod_totals: dict[str, int] = {k: 0 for k in _SYNC_STATUS_ORDER}

    for row in rows:
        status = (row.get("sync_status") or "pending").strip()
        if status not in counts:
            counts[status] = 0
            cod_totals[status] = 0
        counts[status] += 1
        cod_raw = row.get("cod_amount")
        if cod_raw is not None:
            try:
                cod_totals[status] += int(cod_raw)
            except (TypeError, ValueError):
                pass

    breakdown: list[dict[str, Any]] = [
        {"key": key, "count": counts.get(key, 0), "cod_total": cod_totals.get(key, 0)}
        for key in _SYNC_STATUS_ORDER
        if counts.get(key, 0) > 0
    ]
    for key, count in counts.items():
        if count > 0 and key not in _SYNC_STATUS_ORDER:
            breakdown.append({"key": key, "count": count, "cod_total": cod_totals.get(key, 0)})

    total_cod = sum(cod_totals.values())

    unlinked_count = counts.get("unlinked", 0) + counts.get("order_not_found", 0)

    return {
        "total_rows": len(rows),
        "matched": counts.get("matched", 0),
        "in_progress": counts.get("in_progress", 0),
        "mismatch": counts.get("mismatch", 0),
        "unlinked": unlinked_count,
        "order_not_found": counts.get("order_not_found", 0),
        "ems_not_found": counts.get("ems_not_found", 0),
        "parse_error": counts.get("parse_error", 0),
        "total_cod_amount": total_cod,
        "breakdown": breakdown,
    }


def _record_to_dict(record: EmsShippingRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "row_number": record.excel_row_number or 0,
        "reference_code": record.reference_code or "",
        "recipient_label": record.recipient_label or "",
        "order_code": record.order_code,
        "order_id": record.order_id,
        "order_status": record.order_status,
        "current_step_key": record.current_step_key,
        "tracking_number_saved": record.tracking_number_saved,
        "ems_tracking_code": record.ems_tracking_code,
        "ems_reference_code": record.ems_reference_code,
        "ems_status": record.ems_status,
        "ems_phase": record.ems_phase,
        "sync_status": record.sync_status,
        "sync_message": record.sync_message or "",
        "ems_error": record.ems_error,
        "cod_amount": int(record.cod_amount) if record.cod_amount is not None else None,
        "cod_paid_amount": int(record.cod_paid_amount) if record.cod_paid_amount is not None else None,
        "cod_paid_date": record.cod_paid_date.isoformat() if record.cod_paid_date else None,
        "cod_settlement_status": record.cod_settlement_status,
        "cod_settlement_message": record.cod_settlement_message,
        "freight_amount": int(record.freight_amount) if record.freight_amount is not None else None,
        "freight_settled_at": record.freight_settled_at.isoformat() if record.freight_settled_at else None,
        "freight_settlement_status": record.freight_settlement_status,
        "freight_settlement_message": record.freight_settlement_message,
        "freight_high_fee_warning": record.freight_high_fee_warning,
        "order_synced": False,
        "order_sync_message": "",
    }


def _upsert_record(
    db: Session,
    result: dict[str, Any],
    *,
    admin_id: Optional[int] = None,
    source_filename: Optional[str] = None,
) -> tuple[EmsShippingRecord, bool]:
    ref = (result.get("reference_code") or "").strip().upper()
    if not ref:
        raise ValueError("Thiếu mã tham chiếu để lưu bảng vận chuyển.")

    record = db.query(EmsShippingRecord).filter(EmsShippingRecord.reference_code == ref).first()
    created = record is None
    if not record:
        record = EmsShippingRecord(reference_code=ref)
        db.add(record)

    record.recipient_label = result.get("recipient_label") or ""
    record.order_code = result.get("order_code")
    record.order_id = result.get("order_id")
    record.excel_row_number = result.get("row_number")
    record.order_status = result.get("order_status")
    record.current_step_key = result.get("current_step_key")
    record.tracking_number_saved = result.get("tracking_number_saved")
    record.ems_tracking_code = result.get("ems_tracking_code")
    record.ems_reference_code = result.get("ems_reference_code")
    record.ems_status = result.get("ems_status")
    record.ems_phase = result.get("ems_phase")
    record.sync_status = result.get("sync_status") or "pending"
    record.sync_message = result.get("sync_message")
    record.ems_error = result.get("ems_error")
    cod = result.get("cod_amount")
    record.cod_amount = int(cod) if cod is not None else None
    if source_filename:
        record.import_source_filename = source_filename
    if admin_id:
        record.imported_by_admin_id = admin_id
    db.flush()
    return record, created


def _enrich_row_from_live_order(db: Session, row: dict[str, Any]) -> dict[str, Any]:
    """Cập nhật trạng thái đơn shop mới nhất khi hiển thị bảng (không cần import lại)."""
    order_code = (row.get("order_code") or "").strip().upper()
    if not _is_shop_order_code(order_code):
        return row
    order = crud.order.get_order_by_code(db, order_code)
    if not order:
        return row
    row["order_id"] = order.id
    row["order_status"] = getattr(order.status, "value", order.status)
    row["tracking_number_saved"] = order.tracking_number
    step_key, _ = _order_timeline_summary(db, order)
    row["current_step_key"] = step_key
    ems_phase = (row.get("ems_phase") or "").strip()
    if ems_phase and ems_phase != "unknown":
        sync_status, sync_message = _compare_ems_with_order(
            ems_phase=ems_phase,
            order_status=row["order_status"],
            current_step_key=step_key,
        )
        row["sync_status"] = sync_status
        row["sync_message"] = sync_message
    elif (row.get("sync_status") or "") in ("unlinked", "order_not_found"):
        row["sync_status"] = "in_progress"
        row["sync_message"] = (
            f"Đã ghép đơn {order_code} — chưa có hành trình EMS hoặc cần import lại để tra EMS."
        )
    return row


def list_ems_shipping_records(db: Session) -> dict[str, Any]:
    records = (
        db.query(EmsShippingRecord)
        .order_by(EmsShippingRecord.updated_at.desc(), EmsShippingRecord.id.desc())
        .all()
    )
    rows = [_enrich_row_from_live_order(db, _record_to_dict(r)) for r in records]
    return {
        "ok": True,
        "warnings": [],
        "summary": _build_summary(rows),
        "rows": rows,
    }


def delete_ems_shipping_records(db: Session, record_ids: list[int]) -> int:
    ids = [int(x) for x in record_ids if int(x) > 0]
    if not ids:
        return 0
    deleted = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.id.in_(ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return int(deleted or 0)


def import_ems_shipment_excel(
    db: Session,
    file_bytes: bytes,
    *,
    admin_id: Optional[int] = None,
    source_filename: Optional[str] = None,
) -> dict[str, Any]:
    rows, warnings = parse_ems_export_rows(file_bytes)
    rows, dedupe_warnings = _dedupe_rows_by_reference(rows)
    warnings.extend(dedupe_warnings)

    # Luôn import nhanh — tra EMS chạy nền qua ems_tracking_refresh worker.
    warnings.append(
        "Import nhanh: đã lưu mã vận đơn/COD/đơn. Tra EMS sẽ chạy nền trên server theo thứ tự."
    )

    results = [
        process_ems_import_row(db, row, admin_id=admin_id, skip_ems_tracking=True)
        for row in rows
    ]

    created = updated = skipped_no_reference = orders_synced = 0
    imported_record_ids: list[int] = []
    for result in results:
        ref = (result.get("reference_code") or "").strip().upper()
        if not ref:
            skipped_no_reference += 1
            continue
        if result.get("order_synced"):
            orders_synced += 1
        record, was_created = _upsert_record(
            db,
            result,
            admin_id=admin_id,
            source_filename=source_filename,
        )
        imported_record_ids.append(int(record.id))
        if was_created:
            created += 1
        else:
            updated += 1

    db.commit()

    tracking_refresh_job_id = None
    try:
        from app.services import ems_tracking_refresh as ems_refresh_svc

        tracking_refresh_job_id = ems_refresh_svc.enqueue_tracking_refresh(
            imported_record_ids,
            admin_id=admin_id,
            source="import",
        )
    except Exception as exc:
        warnings.append(f"Không khởi chạy job tra EMS nền: {exc}")

    payload = list_ems_shipping_records(db)
    payload["warnings"] = warnings
    payload["import_stats"] = {
        "file_rows_processed": len(results),
        "created": created,
        "updated": updated,
        "skipped_no_reference": skipped_no_reference,
        "orders_synced": orders_synced,
    }
    payload["tracking_refresh_job_id"] = tracking_refresh_job_id
    return payload
