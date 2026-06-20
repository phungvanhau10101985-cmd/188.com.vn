#!/usr/bin/env python3
"""
Xóa một lần import EMS nhầm (vd. file listing_queue_products_*.xlsx vào mục Vận chuyển).

Chạy trên server (thư mục backend):

  # Xem trước — không xóa
  python scripts/delete_wrong_ems_import_batch.py \\
    --filename listing_queue_products_e67f30b31fbc_20260620_082152.xlsx

  # Xóa thật
  python scripts/delete_wrong_ems_import_batch.py \\
    --filename listing_queue_products_e67f30b31fbc_20260620_082152.xlsx \\
    --execute

  # Hoặc theo id batch (xem trong Lịch sử báo cáo import)
  python scripts/delete_wrong_ems_import_batch.py --batch-id 7 --execute

Mặc định chỉ xóa các dòng vận đơn được tạo mới (import_action=created) trong batch đó.
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Xóa batch import EMS nhầm và các vận đơn đã tạo")
    parser.add_argument("--batch-id", type=int, help="ID batch trong ems_shipping_import_batches")
    parser.add_argument(
        "--filename",
        help="Tên file (hoặc một phần), vd. listing_queue_products_e67f30b31fbc_20260620_082152.xlsx",
    )
    parser.add_argument(
        "--include-updated",
        action="store_true",
        help="Xóa cả dòng import_action=updated (mặc định chỉ created)",
    )
    parser.add_argument("--execute", action="store_true", help="Ghi DB — không có flag này thì chỉ xem trước")
    args = parser.parse_args()

    if not args.batch_id and not args.filename:
        parser.error("Cần --batch-id hoặc --filename")

    db_url = str(engine.url)
    host = (engine.url.host or "").lower()
    print("=" * 60)
    print(f" DATABASE: {db_url}")
    if host and host not in ("localhost", "127.0.0.1", "::1"):
        print(f" [!] Host không phải localhost ({host}). Kiểm tra kỹ trước khi xóa.")

    db = SessionLocal()
    try:
        batch = _find_batch(db, batch_id=args.batch_id, filename=args.filename)
        if not batch:
            print("Không tìm thấy batch import khớp điều kiện.")
            return 1

        rows = (
            db.query(EmsShippingImportBatchRow)
            .filter(EmsShippingImportBatchRow.batch_id == batch.id)
            .order_by(EmsShippingImportBatchRow.excel_row_number.asc(), EmsShippingImportBatchRow.id.asc())
            .all()
        )
        allowed_actions = {"created", "updated"} if args.include_updated else {"created"}
        record_ids = sorted(
            {
                int(r.ems_shipping_record_id)
                for r in rows
                if r.ems_shipping_record_id
                and (r.import_action or "created").strip().lower() in allowed_actions
            }
        )

        print(f" Batch id       : {batch.id}")
        print(f" File           : {batch.source_filename}")
        print(f" Thời gian      : {batch.created_at}")
        print(f" Báo cáo        : {batch.order_count} dòng · +{batch.created_count}/~{batch.updated_count}")
        print(f" Tổng COD       : {int(batch.total_cod_amount or 0):,} đ")
        print(f" Sẽ xóa vận đơn : {len(record_ids)} bản ghi (import_action={'created' if not args.include_updated else 'created+updated'})")

        if record_ids:
            sample = (
                db.query(EmsShippingRecord)
                .filter(EmsShippingRecord.id.in_(record_ids[:5]))
                .all()
            )
            print(" Mẫu mã vận đơn:")
            for rec in sample:
                label = (rec.recipient_label or "")[:72]
                if len(rec.recipient_label or "") > 72:
                    label += "…"
                print(f"   - {rec.reference_code} | {label}")

        if not args.execute:
            print("-" * 60)
            print("Chế độ xem trước — không thay đổi DB. Thêm --execute để xóa.")
            return 0

        deleted_records = 0
        if record_ids:
            deleted_records = (
                db.query(EmsShippingRecord)
                .filter(EmsShippingRecord.id.in_(record_ids))
                .delete(synchronize_session=False)
            )
        db.delete(batch)
        db.commit()
        print("-" * 60)
        print(f"Đã xóa {int(deleted_records or 0)} vận đơn và batch #{batch.id}.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
