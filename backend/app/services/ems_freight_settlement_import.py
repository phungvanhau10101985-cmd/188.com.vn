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
_COL_TRACKING = 0  # cột A
_COL_ISSUE_DATE = 2  # cột C — Ngay_Phat_Hanh
_COL_FREIGHT = 11  # cột L
_HIGH_FEE_THRESHOLD = 70_000
_HEADER_TRACKING_NAMES = ("MA_E1", "MA E1", "MA_VAN_CHUYEN", "MA VAN CHUYEN")
_HEADER_ISSUE_DATE_NAMES = (
    "NGAY_PHAT_HANH",
    "NGAY PHAT HANH",
    "NGAY_PH",
    "NGAY PHAT",
)


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


def _find_header_row(raw_rows: list[tuple[Any, ...]]) -> int:
    for idx, row in enumerate(raw_rows[:5]):
        tracking_header = _cell_str(row[_COL_TRACKING] if _COL_TRACKING < len(row) else "").upper()
        if tracking_header in _HEADER_TRACKING_NAMES:
            return idx
    return 0


def _find_issue_date_column(raw_rows: list[tuple[Any, ...]], header_idx: int) -> int:
    if header_idx >= len(raw_rows):
        return _COL_ISSUE_DATE
    header_row = raw_rows[header_idx]
    for col_idx in range(min(len(header_row), 8)):
        header = _cell_str(header_row[col_idx] if col_idx < len(header_row) else "").upper().replace(" ", "_")
        if header in _HEADER_ISSUE_DATE_NAMES or "PHAT_HANH" in header:
            return col_idx
    return _COL_ISSUE_DATE


def _extract_latest_issue_date(
    raw_rows: list[tuple[Any, ...]],
    *,
    header_idx: int,
    issue_col: int,
) -> Optional[date]:
    """Ngày đối soát cước = ngày phát hành gần nhất (lớn nhất) trong cột C."""
    dates: list[date] = []
    for row in raw_rows[header_idx + 1 :]:
        if issue_col >= len(row):
            continue
        parsed = parse_excel_date_cell(row[issue_col])
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

    issue_col = _find_issue_date_column(raw_rows, header_idx)
    settlement_date = _extract_latest_issue_date(raw_rows, header_idx=header_idx, issue_col=issue_col)
    if not settlement_date:
        warnings.append(
            "Không đọc được ngày từ cột C (Ngay_Phat_Hanh) — vẫn import nhưng thiếu ngày đối soát."
        )

    parsed: list[dict[str, Any]] = []
    for row_idx, row in enumerate(raw_rows[header_idx + 1 :], start=header_idx + 2):
        tracking = _cell_str(row[_COL_TRACKING] if _COL_TRACKING < len(row) else "").upper()
        freight_raw = row[_COL_FREIGHT] if _COL_FREIGHT < len(row) else None
        freight_amount = _parse_cod_amount(freight_raw)

        if not tracking and freight_amount is None:
            continue
        if tracking and not _TRACKING_RE.match(tracking):
            continue
        if not tracking:
            continue

        parsed.append(
            {
                "row_number": row_idx,
                "ems_tracking_code": tracking,
                "freight_amount": freight_amount,
            }
        )

    if not parsed:
        warnings.append("Không có dòng dữ liệu hợp lệ (cột A mã vận chuyển / cột L cước phí).")
    return settlement_date, parsed, warnings


def _dedupe_by_tracking(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    by_tracking: dict[str, dict[str, Any]] = {}
    no_tracking: list[dict[str, Any]] = []
    dup_count = 0

    for row in rows:
        tracking = (row.get("ems_tracking_code") or "").strip().upper()
        if not tracking:
            no_tracking.append(row)
            continue
        if tracking in by_tracking:
            dup_count += 1
        by_tracking[tracking] = {**row, "ems_tracking_code": tracking}

    if dup_count:
        warnings.append(
            f"Có {dup_count} dòng trùng mã vận chuyển trong file — giữ dòng cuối cùng."
        )
    deduped = no_tracking + sorted(by_tracking.values(), key=lambda r: r.get("row_number", 0))
    return deduped, warnings


def _find_shipping_by_tracking(db: Session, tracking_code: str) -> Optional[EmsShippingRecord]:
    tracking = (tracking_code or "").strip().upper()
    if not tracking:
        return None
    return (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.ems_tracking_code.ilike(tracking))
        .first()
    )


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
    freight = row.get("freight_amount")
    high_fee = freight is not None and freight > _HIGH_FEE_THRESHOLD

    if freight is None:
        return {
            **row,
            "reconcile_status": "parse_error",
            "reconcile_message": "Không đọc được cước phí (cột L).",
            "high_fee_warning": None,
            "ems_shipping_record_id": None,
        }

    record = _find_shipping_by_tracking(db, tracking)
    if not record:
        return {
            **row,
            "reconcile_status": "record_not_found",
            "reconcile_message": f"Mã {tracking} không tồn tại trong bảng vận chuyển EMS.",
            "high_fee_warning": "yes" if high_fee else None,
            "ems_shipping_record_id": None,
        }

    if _is_already_freight_settled(record):
        when = _date_label(record.freight_settled_at)
        return {
            **row,
            "reconcile_status": "already_settled",
            "reconcile_message": f"Mã {tracking} đã được đối soát cước ({when}).",
            "high_fee_warning": "yes" if high_fee else None,
            "ems_shipping_record_id": record.id,
            "order_code": record.order_code,
            "reference_code": record.reference_code,
        }

    message = f"Đối soát cước {freight:,} ₫ — mã {tracking} hợp lệ."
    if high_fee:
        message += f" Cảnh báo: cước phí > {_HIGH_FEE_THRESHOLD:,} ₫ — cần xem lại."

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
        .order_by(EmsFreightSettlementBatch.created_at.asc(), EmsFreightSettlementBatch.id.asc())
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

    latest_rows = items[-1]["rows"] if items else []
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
            f"Có {summary['high_fee_warning_count']} mã có cước phí > {_HIGH_FEE_THRESHOLD:,} ₫ — vui lòng xem lại."
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
