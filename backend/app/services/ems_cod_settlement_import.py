from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.order_shipment import EmsCodSettlementBatch, EmsCodSettlementRow, EmsShippingRecord
from app.services.ems_excel_utils import parse_excel_date_cell, read_spreadsheet_rows
from app.services.ems_shipment_import import _parse_cod_amount, _cell_str
_TRACKING_RE = re.compile(r"^[A-Z]{2}\d+[A-Z]{2}$", re.IGNORECASE)
_COL_TRACKING = 2  # cột C
_COL_PAID = 3  # cột D
_COL_REFERENCE = 1  # cột B — mã tham chiếu EMS
_PAYMENT_DATE_CELL = (0, 4)  # E1
_DATA_START_ROW = 2  # hàng 3 trong Excel (0-indexed)


def _isoformat_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


def _read_excel_rows(file_bytes: bytes, filename: str) -> list[tuple[Any, ...]]:
    return read_spreadsheet_rows(file_bytes, filename)


def _normalize_source_filename(name: Optional[str]) -> Optional[str]:
    text = (name or "").strip()
    return text.casefold() if text else None


def _find_batches_by_filename(
    db: Session,
    source_filename: Optional[str],
) -> list[EmsCodSettlementBatch]:
    norm = _normalize_source_filename(source_filename)
    if not norm:
        return []
    batches = (
        db.query(EmsCodSettlementBatch)
        .filter(EmsCodSettlementBatch.source_filename.isnot(None))
        .order_by(EmsCodSettlementBatch.id.asc())
        .all()
    )
    return [b for b in batches if _normalize_source_filename(b.source_filename) == norm]


def _clear_settlement_on_shipping_record(db: Session, record_id: Optional[int]) -> None:
    if not record_id:
        return
    shipping = db.query(EmsShippingRecord).filter(EmsShippingRecord.id == record_id).first()
    if not shipping:
        return
    shipping.cod_paid_amount = None
    shipping.cod_paid_date = None
    shipping.cod_settlement_status = None
    shipping.cod_settlement_message = None


def _clear_batch_settlements(db: Session, batch_id: int) -> None:
    rows = (
        db.query(EmsCodSettlementRow)
        .filter(EmsCodSettlementRow.batch_id == batch_id)
        .all()
    )
    for row in rows:
        _clear_settlement_on_shipping_record(db, row.ems_shipping_record_id)
    db.query(EmsCodSettlementRow).filter(EmsCodSettlementRow.batch_id == batch_id).delete(
        synchronize_session=False
    )


def parse_cod_settlement_rows(
    file_bytes: bytes,
    *,
    source_filename: Optional[str] = None,
) -> tuple[Optional[date], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    raw_rows = _read_excel_rows(file_bytes, source_filename or "")
    if not raw_rows:
        return None, [], ["File Excel trống."]

    pay_row, pay_col = _PAYMENT_DATE_CELL
    e1_raw = raw_rows[pay_row][pay_col] if pay_row < len(raw_rows) and pay_col < len(raw_rows[pay_row]) else None
    payment_date = parse_excel_date_cell(e1_raw)
    if not payment_date:
        warnings.append(
            "Không đọc được ngày trả tiền từ ô E1 (vd. «Ngày trả tiền: 02/06/2026») — vẫn import nhưng thiếu ngày."
        )

    parsed: list[dict[str, Any]] = []
    for row_idx, row in enumerate(raw_rows[_DATA_START_ROW:], start=_DATA_START_ROW + 1):
        tracking = _cell_str(row[_COL_TRACKING] if _COL_TRACKING < len(row) else "").upper()
        reference = _cell_str(row[_COL_REFERENCE] if _COL_REFERENCE < len(row) else "").upper()
        paid_raw = row[_COL_PAID] if _COL_PAID < len(row) else None
        paid_amount = _parse_cod_amount(paid_raw)

        if not tracking and not reference and paid_amount is None:
            continue
        if tracking and not _TRACKING_RE.match(tracking):
            continue
        if not tracking:
            if reference or paid_amount is not None:
                parsed.append(
                    {
                        "row_number": row_idx,
                        "ems_reference_code": reference or None,
                        "ems_tracking_code": None,
                        "paid_amount": paid_amount,
                        "reconcile_status": "parse_error",
                        "reconcile_message": "Thiếu mã vận chuyển EMS (cột C).",
                    }
                )
            continue

        parsed.append(
            {
                "row_number": row_idx,
                "ems_reference_code": reference or None,
                "ems_tracking_code": tracking,
                "paid_amount": paid_amount,
            }
        )

    if not parsed:
        warnings.append("Không có dòng dữ liệu hợp lệ (cột C mã vận chuyển / cột D số tiền).")
    return payment_date, parsed, warnings


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


def _find_shipping_record(
    db: Session,
    *,
    tracking_code: str,
    reference_code: Optional[str],
) -> Optional[EmsShippingRecord]:
    tracking = (tracking_code or "").strip().upper()
    if tracking:
        record = (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.ems_tracking_code.ilike(tracking))
            .first()
        )
        if record:
            return record

    ref = (reference_code or "").strip().upper()
    if ref:
        return (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.reference_code.ilike(ref))
            .first()
        )
    return None


def _reconcile_row(
    db: Session,
    row: dict[str, Any],
) -> dict[str, Any]:
    if row.get("reconcile_status") == "parse_error":
        return row

    tracking = (row.get("ems_tracking_code") or "").strip().upper()
    paid = row.get("paid_amount")
    if paid is None:
        return {
            **row,
            "reconcile_status": "parse_error",
            "reconcile_message": "Không đọc được số tiền đã trả (cột D).",
            "ems_shipping_record_id": None,
            "db_cod_amount": None,
            "amount_difference": None,
        }

    record = _find_shipping_record(
        db,
        tracking_code=tracking,
        reference_code=row.get("ems_reference_code"),
    )
    if not record:
        return {
            **row,
            "reconcile_status": "record_not_found",
            "reconcile_message": f"Không tìm thấy mã {tracking} trong bảng vận chuyển EMS.",
            "ems_shipping_record_id": None,
            "db_cod_amount": None,
            "amount_difference": None,
        }

    db_cod = int(record.cod_amount) if record.cod_amount is not None else None
    effective_db = db_cod if db_cod is not None else 0

    if paid == 0 and effective_db == 0:
        return {
            **row,
            "reconcile_status": "matched",
            "reconcile_message": "Đơn không thu hộ (0 ₫) — khớp.",
            "ems_shipping_record_id": record.id,
            "db_cod_amount": db_cod if db_cod is not None else 0,
            "amount_difference": 0,
            "order_code": record.order_code,
            "reference_code": record.reference_code,
        }

    diff = paid - effective_db

    if db_cod is None:
        status = "amount_mismatch"
        message = f"Đã trả {paid:,} ₫ nhưng bản ghi EMS chưa có tiền thu hộ trong file gửi EMS."
    elif paid == db_cod:
        status = "matched"
        message = f"Khớp: thu hộ {db_cod:,} ₫ = đã trả {paid:,} ₫."
    else:
        status = "amount_mismatch"
        sign = "+" if diff > 0 else ""
        message = (
            f"Lệch tiền: thu hộ DB {db_cod:,} ₫, file trả {paid:,} ₫ "
            f"(chênh {sign}{diff:,} ₫)."
        )

    return {
        **row,
        "reconcile_status": status,
        "reconcile_message": message,
        "ems_shipping_record_id": record.id,
        "db_cod_amount": db_cod,
        "amount_difference": diff,
        "order_code": record.order_code,
        "reference_code": record.reference_code,
    }


def _row_to_dict(row: EmsCodSettlementRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "batch_id": row.batch_id,
        "row_number": row.excel_row_number or 0,
        "ems_reference_code": row.ems_reference_code,
        "ems_tracking_code": row.ems_tracking_code,
        "paid_amount": int(row.paid_amount) if row.paid_amount is not None else None,
        "ems_shipping_record_id": row.ems_shipping_record_id,
        "db_cod_amount": int(row.db_cod_amount) if row.db_cod_amount is not None else None,
        "amount_difference": int(row.amount_difference) if row.amount_difference is not None else None,
        "reconcile_status": row.reconcile_status,
        "reconcile_message": row.reconcile_message or "",
    }


def _batch_to_dict(batch: EmsCodSettlementBatch, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": batch.id,
        "payment_date": _isoformat_value(batch.payment_date),
        "source_filename": batch.source_filename,
        "total_rows": batch.total_rows,
        "matched_count": batch.matched_count,
        "amount_mismatch_count": batch.amount_mismatch_count,
        "record_not_found_count": batch.record_not_found_count,
        "parse_error_count": batch.parse_error_count,
        "total_paid_amount": int(batch.total_paid_amount or 0),
        "total_db_cod_amount": int(batch.total_db_cod_amount or 0),
        "total_amount_difference": int(batch.total_amount_difference or 0),
        "created_at": _isoformat_value(batch.created_at),
        "rows": rows,
    }


def _build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    paid_totals: dict[str, int] = {}
    db_totals: dict[str, int] = {}

    for row in rows:
        key = row.get("reconcile_status") or "pending"
        counts[key] = counts.get(key, 0) + 1
        paid = row.get("paid_amount") or 0
        paid_totals[key] = paid_totals.get(key, 0) + paid
        db = row.get("db_cod_amount")
        if db is not None:
            db_totals[key] = db_totals.get(key, 0) + db

    order = ("matched", "amount_mismatch", "record_not_found", "parse_error")
    breakdown = [
        {
            "key": key,
            "count": counts.get(key, 0),
            "paid_total": paid_totals.get(key, 0),
            "db_cod_total": db_totals.get(key, 0),
        }
        for key in order
        if counts.get(key, 0)
    ]

    total_paid = sum(paid_totals.values())
    total_db = sum(db_totals.values())
    total_diff = sum(
        row.get("amount_difference") or 0
        for row in rows
        if row.get("reconcile_status") == "amount_mismatch"
    )

    return {
        "total_rows": len(rows),
        "matched": counts.get("matched", 0),
        "amount_mismatch": counts.get("amount_mismatch", 0),
        "record_not_found": counts.get("record_not_found", 0),
        "parse_error": counts.get("parse_error", 0),
        "total_paid_amount": total_paid,
        "total_db_cod_amount": total_db,
        "total_amount_difference": total_diff,
        "breakdown": breakdown,
    }


def _apply_settlement_to_shipping_record(
    db: Session,
    record_id: Optional[int],
    *,
    paid_amount: Optional[int],
    payment_date: Optional[date],
    status: str,
    message: str,
) -> None:
    if not record_id:
        return
    shipping = db.query(EmsShippingRecord).filter(EmsShippingRecord.id == record_id).first()
    if not shipping:
        return
    if paid_amount is not None:
        shipping.cod_paid_amount = paid_amount
    if payment_date:
        shipping.cod_paid_date = payment_date
    shipping.cod_settlement_status = status
    shipping.cod_settlement_message = message


def list_cod_settlement_batches(db: Session, *, limit: int = 100) -> dict[str, Any]:
    batches = (
        db.query(EmsCodSettlementBatch)
        .order_by(EmsCodSettlementBatch.payment_date.desc(), EmsCodSettlementBatch.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for batch in batches:
        rows = (
            db.query(EmsCodSettlementRow)
            .filter(EmsCodSettlementRow.batch_id == batch.id)
            .order_by(EmsCodSettlementRow.excel_row_number.asc(), EmsCodSettlementRow.id.asc())
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


def import_cod_settlement_excel(
    db: Session,
    file_bytes: bytes,
    *,
    admin_id: Optional[int] = None,
    source_filename: Optional[str] = None,
) -> dict[str, Any]:
    payment_date, rows, warnings = parse_cod_settlement_rows(file_bytes, source_filename=source_filename)
    rows, dedupe_warnings = _dedupe_by_tracking(rows)
    warnings.extend(dedupe_warnings)

    reconciled = [_reconcile_row(db, row) for row in rows]
    summary = _build_summary(reconciled)

    effective_payment_date = payment_date or date.today()

    matching_batches = _find_batches_by_filename(db, source_filename)
    if matching_batches:
        batch = matching_batches[0]
        for dup in matching_batches[1:]:
            _clear_batch_settlements(db, dup.id)
            db.delete(dup)
        _clear_batch_settlements(db, batch.id)
        batch.payment_date = effective_payment_date
        batch.source_filename = source_filename
        batch.imported_by_admin_id = admin_id
        batch.total_rows = summary["total_rows"]
        batch.matched_count = summary["matched"]
        batch.amount_mismatch_count = summary["amount_mismatch"]
        batch.record_not_found_count = summary["record_not_found"]
        batch.parse_error_count = summary["parse_error"]
        batch.total_paid_amount = summary["total_paid_amount"]
        batch.total_db_cod_amount = summary["total_db_cod_amount"]
        batch.total_amount_difference = summary["total_amount_difference"]
        db.flush()
        warnings.append(
            f"File «{source_filename}» đã import trước đó — cập nhật đợt #{batch.id}, không tạo đợt mới."
        )
    else:
        batch = EmsCodSettlementBatch(
            payment_date=effective_payment_date,
            source_filename=source_filename,
            imported_by_admin_id=admin_id,
            total_rows=summary["total_rows"],
            matched_count=summary["matched"],
            amount_mismatch_count=summary["amount_mismatch"],
            record_not_found_count=summary["record_not_found"],
            parse_error_count=summary["parse_error"],
            total_paid_amount=summary["total_paid_amount"],
            total_db_cod_amount=summary["total_db_cod_amount"],
            total_amount_difference=summary["total_amount_difference"],
        )
        db.add(batch)
        db.flush()

    saved_rows: list[dict[str, Any]] = []
    for row in reconciled:
        settlement_row = EmsCodSettlementRow(
            batch_id=batch.id,
            excel_row_number=row.get("row_number"),
            ems_reference_code=row.get("ems_reference_code"),
            ems_tracking_code=row.get("ems_tracking_code"),
            paid_amount=row.get("paid_amount"),
            ems_shipping_record_id=row.get("ems_shipping_record_id"),
            db_cod_amount=row.get("db_cod_amount"),
            amount_difference=row.get("amount_difference"),
            reconcile_status=row.get("reconcile_status") or "pending",
            reconcile_message=row.get("reconcile_message"),
        )
        db.add(settlement_row)
        _apply_settlement_to_shipping_record(
            db,
            row.get("ems_shipping_record_id"),
            paid_amount=row.get("paid_amount"),
            payment_date=effective_payment_date,
            status=row.get("reconcile_status") or "pending",
            message=row.get("reconcile_message") or "",
        )
        db.flush()
        saved_rows.append(_row_to_dict(settlement_row))

    db.commit()

    payload = list_cod_settlement_batches(db, limit=100)
    payload["warnings"] = warnings
    payload["import_batch"] = _batch_to_dict(batch, saved_rows)
    payload["summary"] = _build_summary(saved_rows)
    return payload
