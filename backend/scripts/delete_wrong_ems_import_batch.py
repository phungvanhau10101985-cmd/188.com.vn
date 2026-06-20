#!/usr/bin/env python3
"""
Xóa một lần import EMS nhầm (vd. file listing_queue_products_*.xlsx vào mục Vận chuyển).

Chạy trên server (thư mục backend):

  cd /var/www/188.com.vn/backend

  # 1) Xem trước — phải thấy ~156 dòng
  PYTHONPATH=. .venv/bin/python scripts/delete_wrong_ems_import_batch.py \\
    --filename listing_queue_products_e67f30b31fbc_20260620_082152.xlsx

  # 2) Xóa thật
  PYTHONPATH=. .venv/bin/python scripts/delete_wrong_ems_import_batch.py \\
    --filename listing_queue_products_e67f30b31fbc_20260620_082152.xlsx \\
    --execute

  # Hoặc chỉ cần một phần tên file
  PYTHONPATH=. .venv/bin/python scripts/delete_wrong_ems_import_batch.py \\
    --import-source-contains listing_queue_products_e67f30b31fbc --execute

Mặc định chỉ xóa các dòng vận đơn được tạo mới (import_action=created) trong batch đó,
và mọi bản ghi ems_shipping_records có import_source_filename khớp.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import func  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.order_shipment import (  # noqa: E402
    EmsShippingImportBatch,
    EmsShippingImportBatchRow,
    EmsShippingRecord,
)


def _find_batch(
    db,
    *,
    batch_id: Optional[int],
    filename: Optional[str],
) -> Optional[EmsShippingImportBatch]:
    if batch_id:
        return db.query(EmsShippingImportBatch).filter(EmsShippingImportBatch.id == int(batch_id)).first()
    if filename:
        needle = filename.strip()
        return (
            db.query(EmsShippingImportBatch)
            .filter(EmsShippingImportBatch.source_filename.ilike(f"%{needle}%"))
            .order_by(EmsShippingImportBatch.created_at.desc(), EmsShippingImportBatch.id.desc())
            .first()
        )
    return None


def _record_ids_from_batch(
    db,
    batch: EmsShippingImportBatch,
    *,
    include_updated: bool,
) -> set[int]:
    rows = (
        db.query(EmsShippingImportBatchRow)
        .filter(EmsShippingImportBatchRow.batch_id == batch.id)
        .all()
    )
    allowed_actions = {"created", "updated"} if include_updated else {"created"}
    return {
        int(r.ems_shipping_record_id)
        for r in rows
        if r.ems_shipping_record_id
        and (r.import_action or "created").strip().lower() in allowed_actions
    }


def _record_ids_from_import_source(db, needle: str) -> set[int]:
    text = (needle or "").strip()
    if not text:
        return set()
    rows = (
        db.query(EmsShippingRecord.id)
        .filter(EmsShippingRecord.import_source_filename.ilike(f"%{text}%"))
        .all()
    )
    return {int(row[0]) for row in rows}


def _print_samples(db, record_ids: list[int], *, limit: int = 5) -> None:
    if not record_ids:
        return
    sample = (
        db.query(EmsShippingRecord)
        .filter(EmsShippingRecord.id.in_(record_ids[:limit]))
        .all()
    )
    print(" Mẫu mã vận đơn:")
    for rec in sample:
        label = (rec.recipient_label or "")[:72]
        if len(rec.recipient_label or "") > 72:
            label += "…"
        cod = int(rec.cod_amount or 0)
        print(f"   - {rec.reference_code} | COD {cod:,} đ | {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Xóa batch import EMS nhầm và các vận đơn đã tạo")
    parser.add_argument("--batch-id", type=int, help="ID batch trong ems_shipping_import_batches")
    parser.add_argument(
        "--filename",
        help="Tên file (hoặc một phần), vd. listing_queue_products_e67f30b31fbc_20260620_082152.xlsx",
    )
    parser.add_argument(
        "--import-source-contains",
        help="Xóa mọi vận đơn có import_source_filename chứa chuỗi này (vd. listing_queue_products_e67f30b31fbc)",
    )
    parser.add_argument(
        "--include-updated",
        action="store_true",
        help="Xóa cả dòng import_action=updated (mặc định chỉ created)",
    )
    parser.add_argument("--execute", action="store_true", help="Ghi DB — không có flag này thì chỉ xem trước")
    args = parser.parse_args()

    if not args.batch_id and not args.filename and not args.import_source_contains:
        parser.error("Cần --batch-id, --filename hoặc --import-source-contains")

    db_url = str(engine.url)
    host = (engine.url.host or "").lower()
    print("=" * 60)
    print(f" DATABASE: {db_url}")
    if host and host not in ("localhost", "127.0.0.1", "::1"):
        print(f" [!] Host không phải localhost ({host}). Kiểm tra kỹ trước khi xóa.")

    db = SessionLocal()
    try:
        batch = _find_batch(db, batch_id=args.batch_id, filename=args.filename)
        record_ids: set[int] = set()

        if batch:
            record_ids |= _record_ids_from_batch(db, batch, include_updated=args.include_updated)
            print(f" Batch id       : {batch.id}")
            print(f" File           : {batch.source_filename}")
            print(f" Thời gian      : {batch.created_at}")
            print(f" Báo cáo        : {batch.order_count} dòng · +{batch.created_count}/~{batch.updated_count}")
            print(f" Tổng COD batch : {int(batch.total_cod_amount or 0):,} đ")
        else:
            print(" Batch import   : (không tìm thấy — sẽ xóa theo import_source_filename nếu có)")

        source_needle = (args.import_source_contains or args.filename or "").strip()
        if source_needle:
            from_source = _record_ids_from_import_source(db, source_needle)
            added = from_source - record_ids
            record_ids |= from_source
            if added:
                print(f" Thêm từ import_source_filename (*{source_needle}*): +{len(added)} bản ghi")

        record_ids_sorted = sorted(record_ids)
        if not record_ids_sorted:
            print("Không có vận đơn nào khớp điều kiện.")
            return 1

        total_cod = (
            db.query(func.coalesce(func.sum(EmsShippingRecord.cod_amount), 0))
            .filter(EmsShippingRecord.id.in_(record_ids_sorted))
            .scalar()
        )
        print(f" Sẽ xóa vận đơn : {len(record_ids_sorted)} bản ghi")
        print(f" Tổng COD       : {int(total_cod or 0):,} đ")
        _print_samples(db, record_ids_sorted)

        if not args.execute:
            print("-" * 60)
            print("Chế độ xem trước — không thay đổi DB. Thêm --execute để xóa.")
            return 0

        deleted_records = (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.id.in_(record_ids_sorted))
            .delete(synchronize_session=False)
        )
        if batch:
            db.delete(batch)
        db.commit()
        print("-" * 60)
        msg = f"Đã xóa {int(deleted_records or 0)} vận đơn"
        if batch:
            msg += f" và batch import #{batch.id}"
        msg += "."
        print(msg)
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
