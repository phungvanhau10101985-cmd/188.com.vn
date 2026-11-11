from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.order_shipment import (
    EmsFreightSettlementBatch,
    EmsFreightSettlementRow,
    EmsShippingRecord,
)
from app.services.ems_excel_utils import parse_excel_date_cell, read_spreadsheet_rows
from app.services.ems_shipment_import import _parse_cod_amount, _cell_str

_TRACKING_RE = re.compile(r"^[A-Z]{2}\d+[A-Z]{2}$", re.IGNORECASE)
_COL_TRACKING = 0  # cột A — Ma_E1 / mã đơn
_COL_SHIP_DATE = 1  # cột B — ngày gửi hàng (Ngay_Phat_Hanh)
_COL_FREIGHT = 11  # cột L — cước (Cuoc_Chinh)
_COL_REFERENCE = 22  # cột W — So_Tham_Chieu
_HIGH_FEE_THRESHOLD = 70_000
_HEADER_TRACKING_NAMES = ("MA_E1", "MA E1", "MA_VAN_CHUYEN", "MA VAN CHUYEN")
_HEADER_SHIP_DATE_NAMES = (
    "NGAY_PHAT_HANH",
    "NGAY PHAT HANH",
    "NGAY_GUI_HANG",
    "NGAY GUI HANG",
    "NGAY_GUI",
    "NGAY_PH",
    "NGAY PHAT",
)
_HEADER_FREIGHT_NAMES = ("CUOC_CHINH", "CUOC_PHI", "CUOC")
_HEADER_REFERENCE_NAMES = ("SO_THAM_CHIEU", "MA_THAM_CHIEU", "MA THAM CHIEU")


def _isoformat_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _date_label(value: Any, *, fallback: str = "trước đó") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value[:10] if len(value) >= 10 else value
    date_fn = getattr(value, "date", None)
    if callable(date_fn):
        return date_fn().isoformat()
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _header_key(value: Any) -> str:
    return _cell_str(value).upper().replace(" ", "_")


def _find_header_row(raw_rows: list[tuple[Any, ...]]) -> int:
    for idx, row in enumerate(raw_rows[:8]):
        tracking_header = _header_key(row[_COL_TRACKING] if _COL_TRACKING < len(row) else "")
        if tracking_header in _HEADER_TRACKING_NAMES or tracking_header.replace("_", " ") in _HEADER_TRACKING_NAMES:
            return idx
    return 0


def _find_column(
    header_row: tuple[Any, ...],
    names: tuple[str, ...],
    default: int,
    *,
    contains: tuple[str, ...] = (),
) -> int:
    normalized = tuple(name.upper().replace(" ", "_") for name in names)
    for col_idx, cell in enumerate(header_row):
        header = _header_key(cell)
        if not header:
            continue
        if header in normalized or any(token in header for token in contains):
            return col_idx
    return default


def _clean_code(value: Any, header_names: tuple[str, ...]) -> str:
    code = _cell_str(value).upper()
    if not code:
        return ""
    key = code.replace(" ", "_")
    blocked = {name.upper().replace(" ", "_") for name in header_names}
    if key in blocked:
        return ""
    return code


def _extract_latest_ship_date(
    raw_rows: list[tuple[Any, ...]],
    *,
    header_idx: int,
    ship_col: int,
) -> Optional[date]:
    """Ngày đối soát cước = ngày gửi hàng gần nhất (lớn nhất) trong cột B."""
    dates: list[date] = []
    for row in raw_rows[header_idx + 1 :]:
        if ship_col >= len(row):
            continue
        parsed = parse_excel_date_cell(row[ship_col])
        if parsed:
            dates.append(parsed)
    if not dates:
        return None
    return max(dates)


def parse_freight_settlement_rows(
    file_bytes: bytes,
    *,
    source_filename: Optional[str] = None,
) -> tuple[Optional[date], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    raw_rows = read_spreadsheet_rows(file_bytes, source_filename or "")
    if not raw_rows:
        return None, [], ["File Excel trống."]

    header_idx = _find_header_row(raw_rows)
    if header_idx > 0:
        warnings.append(f"Phát hiện dòng tiêu đề ở hàng {header_idx + 1}.")

    header_row = raw_rows[header_idx] if header_idx < len(raw_rows) else ()
    ship_col = _find_column(
        header_row,
        _HEADER_SHIP_DATE_NAMES,
        _COL_SHIP_DATE,
        contains=("PHAT_HANH", "GUI_HANG"),
    )
    freight_col = _find_column(header_row, _HEADER_FREIGHT_NAMES, _COL_FREIGHT)
    reference_col = _find_column(
        header_row,
        _HEADER_REFERENCE_NAMES,
        _COL_REFERENCE,
        contains=("THAM_CHIEU",),
    )
    settlement_date = _extract_latest_ship_date(raw_rows, header_idx=header_idx, ship_col=ship_col)
    if not settlement_date:
        warnings.append(
            "Không đọc được ngày từ cột B (ngày gửi hàng) — vẫn import nhưng thiếu ngày đối soát."
        )

    parsed: list[dict[str, Any]] = []
    for row_idx, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        tracking = _clean_code(
            row[_COL_TRACKING] if _COL_TRACKING < len(row) else "",
            _HEADER_TRACKING_NAMES,
        )
        reference = _clean_code(
            row[reference_col] if reference_col < len(row) else "",
            _HEADER_REFERENCE_NAMES,
        )
        freight_raw = row[freight_col] if freight_col < len(row) else None
        freight_amount = _parse_cod_amount(freight_raw)

        if not tracking and not reference and freight_amount is None:
            continue
        if tracking and not _TRACKING_RE.match(tracking):
            tracking = ""
        if not tracking and not reference:
            continue

        parsed.append(
            {
                "row_number": row_idx,
                "ems_tracking_code": tracking or None,
                "reference_code": reference or None,
                "freight_amount": freight_amount,
            }
        )

    if not parsed:
        warnings.append(
            "Không có dòng dữ liệu hợp lệ (cột A mã đơn / cột W mã tham chiếu / cột L cước)."
        )
    return settlement_date, parsed, warnings


def _row_identity(row: dict[str, Any]) -> str:
    tracking = (row.get("ems_tracking_code") or "").strip().upper()
    reference = (row.get("reference_code") or "").strip().upper()
    return tracking or reference


def _code_label(tracking: str, reference: str) -> str:
    if tracking and reference:
        return f"{tracking} (tham chiếu {reference})"
    return tracking or reference or "—"


def _dedupe_by_tracking(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    no_key: list[dict[str, Any]] = []
    dup_count = 0

    for row in rows:
        key = _row_identity(row)
        if not key:
            no_key.append(row)
            continue
        if key in by_key:
            dup_count += 1
        by_key[key] = {
            **row,
            "ems_tracking_code": (row.get("ems_tracking_code") or "").strip().upper() or None,
            "reference_code": (row.get("reference_code") or "").strip().upper() or None,
        }

    if dup_count:
        warnings.append(
            f"Có {dup_count} dòng trùng mã đơn hoặc mã tham chiếu trong file — giữ dòng cuối cùng."
        )
    deduped = no_key + sorted(by_key.values(), key=lambda r: r.get("row_number", 0))
    return deduped, warnings


def _first_shipping_match(db: Session, column: Any, code: str) -> Optional[EmsShippingRecord]:
    text = (code or "").strip()
    if not text:
        return None
    return db.query(EmsShippingRecord).filter(column.ilike(text)).first()


def _find_shipping_for_freight(
    db: Session,
    *,
    tracking_code: str,
    reference_code: str,
) -> Optional[EmsShippingRecord]:
    """Khớp mã đơn (cột A / Ma_E1) hoặc mã tham chiếu (cột W)."""
    reference = (reference_code or "").strip().upper()
    tracking = (tracking_code or "").strip().upper()
    if reference:
        record = _first_shipping_match(db, EmsShippingRecord.reference_code, reference)
        if record:
            return record
        record = _first_shipping_match(db, EmsShippingRecord.ems_reference_code, reference)
        if record:
            return record
    if tracking:
        record = _first_shipping_match(db, EmsShippingRecord.ems_tracking_code, tracking)
        if record:
            return record
        record = _first_shipping_match(db, EmsShippingRecord.reference_code, tracking)
        if record:
            return record
    if reference:
        return _first_shipping_match(db, EmsShippingRecord.ems_tracking_code, reference)
    return None


def _is_already_freight_settled(record: EmsShippingRecord) -> bool:
    if record.freight_settled_at is not None:
        return True
    if (record.freight_settlement_status or "").strip().lower() == "settled":
        return True
    return False


def _reconcile_row(db: Session, row: dict[str, Any]) -> dict[str, Any]:
    if row.get("reconcile_status") == "parse_error":
        return {**row, "high_fee_warning": None, "ems_shipping_record_id": None}

    tracking = (row.get("ems_tracking_code") or "").strip().upper()
    reference = (row.get("reference_code") or "").strip().upper()
    label = _code_label(tracking, reference)
    freight = row.get("freight_amount")
    high_fee = freight is not None and freight > _HIGH_FEE_THRESHOLD

    if freight is None:
        return {
            **row,
            "reconcile_status": "parse_error",
            "reconcile_message": "Không đọc được cước (cột L).",
            "high_fee_warning": None,
            "ems_shipping_record_id": None,
        }

    record = _find_shipping_for_freight(db, tracking_code=tracking, reference_code=reference)
    if not record:
        return {
            **row,
            "reconcile_status": "record_not_found",
            "reconcile_message": f"Không tìm thấy mã {label} trong bảng vận chuyển EMS.",
            "high_fee_warning": "yes" if high_fee else None,
            "ems_shipping_record_id": None,
        }

    if _is_already_freight_settled(record):
        when = _date_label(record.freight_settled_at)
        return {
            **row,
            "reconcile_status": "already_settled",
            "reconcile_message": f"Mã {label} đã được đối soát cước ({when}).",
            "high_fee_warning": "yes" if high_fee else None,
            "ems_shipping_record_id": record.id,
            "order_code": record.order_code,
            "reference_code": record.reference_code or reference or None,
        }

    message = f"Đối soát cước {freight:,} ₫ — mã {label} hợp lệ."
    if high_fee:
        message += f" Cảnh báo: cước > {_HIGH_FEE_THRESHOLD:,} ₫ — cần xem lại."

    return {
        **row,
        "reconcile_status": "settled",
        "reconcile_message": message,
        "high_fee_warning": "yes" if high_fee else None,
        "ems_shipping_record_id": record.id,
        "order_code": record.order_code,
        "reference_code": record.reference_code,
    }


def _row_to_dict(row: EmsFreightSettlementRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "row_number": row.excel_row_number or 0,
        "ems_tracking_code": row.ems_tracking_code,
        "freight_amount": int(row.freight_amount) if row.freight_amount is not None else None,
        "ems_shipping_record_id": row.ems_shipping_record_id,
        "high_fee_warning": row.high_fee_warning,
        "reconcile_status": row.reconcile_status,
        "reconcile_message": row.reconcile_message or "",
    }


def _batch_to_dict(batch: EmsFreightSettlementBatch, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": batch.id,
        "settlement_date": _isoformat_value(batch.settlement_date),
        "source_filename": batch.source_filename,
        "total_rows": batch.total_rows,
        "settled_count": batch.settled_count,
        "record_not_found_count": batch.record_not_found_count,
        "already_settled_count": batch.already_settled_count,
        "parse_error_count": batch.parse_error_count,
        "high_fee_warning_count": batch.high_fee_warning_count,
        "total_freight_amount": int(batch.total_freight_amount or 0),
        "created_at": _isoformat_value(batch.created_at),
        "rows": rows,
    }


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    freight_totals: dict[str, int] = {}
    high_fee_count = 0

    for row in rows:
        key = row.get("reconcile_status") or "pending"
        counts[key] = counts.get(key, 0) + 1
        freight = row.get("freight_amount") or 0
        if row.get("reconcile_status") == "settled":
            freight_totals["settled"] = freight_totals.get("settled", 0) + freight
        if row.get("high_fee_warning") == "yes":
            high_fee_count += 1

    order = ("settled", "already_settled", "record_not_found", "parse_error")
    breakdown = [
        {
            "key": key,
            "count": counts.get(key, 0),
            "freight_total": freight_totals.get(key, 0) if key == "settled" else sum(
                row.get("freight_amount") or 0 for row in rows if row.get("reconcile_status") == key
            ),
        }
        for key in order
        if counts.get(key, 0)
    ]

    return {
        "total_rows": len(rows),
        "settled": counts.get("settled", 0),
        "already_settled": counts.get("already_settled", 0),
        "record_not_found": counts.get("record_not_found", 0),
        "parse_error": counts.get("parse_error", 0),
        "high_fee_warning_count": high_fee_count,
        "total_freight_amount": sum(freight_totals.values()),
        "breakdown": breakdown,
    }


def _apply_settlement_to_shipping_record(
    db: Session,
    record_id: Optional[int],
    *,
    freight_amount: Optional[int],
    high_fee: bool,
    message: str,
) -> None:
    if not record_id:
        return
    shipping = db.query(EmsShippingRecord).filter(EmsShippingRecord.id == record_id).first()
    if not shipping:
        return
    if freight_amount is not None:
        shipping.freight_amount = freight_amount
    shipping.freight_settled_at = datetime.now(timezone.utc)
    shipping.freight_settlement_status = "settled"
    shipping.freight_settlement_message = message
    shipping.freight_high_fee_warning = "yes" if high_fee else None


def list_freight_settlement_batches(db: Session, *, limit: int = 100) -> dict[str, Any]:
    batches = (
        db.query(EmsFreightSettlementBatch)
        .order_by(
            EmsFreightSettlementBatch.settlement_date.desc().nullslast(),
            EmsFreightSettlementBatch.created_at.desc(),
            EmsFreightSettlementBatch.id.desc(),
        )
        .limit(limit)
        .all()
    )
    items = []
    for batch in batches:
        rows = (
            db.query(EmsFreightSettlementRow)
            .filter(EmsFreightSettlementRow.batch_id == batch.id)
            .order_by(EmsFreightSettlementRow.excel_row_number.asc(), EmsFreightSettlementRow.id.asc())
            .all()
        )
        row_dicts = [_row_to_dict(r) for r in rows]
        items.append(_batch_to_dict(batch, row_dicts))

    latest_rows = items[0]["rows"] if items else []
    return {
        "ok": True,
        "warnings": [],
        "summary": _build_summary(latest_rows),
        "batches": items,
    }


def import_freight_settlement_excel(
    db: Session,
    file_bytes: bytes,
    *,
    admin_id: Optional[int] = None,
    source_filename: Optional[str] = None,
) -> dict[str, Any]:
    settlement_date, rows, warnings = parse_freight_settlement_rows(
        file_bytes, source_filename=source_filename
    )
    rows, dedupe_warnings = _dedupe_by_tracking(rows)
    warnings.extend(dedupe_warnings)

    reconciled = [_reconcile_row(db, row) for row in rows]
    summary = _build_summary(reconciled)

    if summary["record_not_found"] or summary["already_settled"] or summary["parse_error"]:
        warnings.append(
            "Một số mã không import được: phải tồn tại trong DB và chưa từng đối soát cước."
        )
    if summary["high_fee_warning_count"]:
        warnings.append(
            f"Có {summary['high_fee_warning_count']} mã có cước > {_HIGH_FEE_THRESHOLD:,} ₫ — vui lòng xem lại."
        )

    batch = EmsFreightSettlementBatch(
        settlement_date=settlement_date,
        source_filename=source_filename,
        imported_by_admin_id=admin_id,
        total_rows=summary["total_rows"],
        settled_count=summary["settled"],
        record_not_found_count=summary["record_not_found"],
        already_settled_count=summary["already_settled"],
        parse_error_count=summary["parse_error"],
        high_fee_warning_count=summary["high_fee_warning_count"],
        total_freight_amount=summary["total_freight_amount"],
    )
    db.add(batch)
    db.flush()

    saved_rows: list[dict[str, Any]] = []
    for row in reconciled:
        settlement_row = EmsFreightSettlementRow(
            batch_id=batch.id,
            excel_row_number=row.get("row_number"),
            ems_tracking_code=row.get("ems_tracking_code"),
            freight_amount=row.get("freight_amount"),
            ems_shipping_record_id=row.get("ems_shipping_record_id"),
            high_fee_warning=row.get("high_fee_warning"),
            reconcile_status=row.get("reconcile_status") or "pending",
            reconcile_message=row.get("reconcile_message"),
        )
        db.add(settlement_row)

        if row.get("reconcile_status") == "settled":
            _apply_settlement_to_shipping_record(
                db,
                row.get("ems_shipping_record_id"),
                freight_amount=row.get("freight_amount"),
                high_fee=row.get("high_fee_warning") == "yes",
                message=row.get("reconcile_message") or "",
            )
        db.flush()
        saved_rows.append(_row_to_dict(settlement_row))

    db.commit()

    payload = list_freight_settlement_batches(db, limit=100)
    payload["warnings"] = warnings
    payload["import_batch"] = _batch_to_dict(batch, saved_rows)
    payload["summary"] = _build_summary(saved_rows)
    return payload
