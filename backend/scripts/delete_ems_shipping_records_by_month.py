"""
Xóa bản ghi vận chuyển EMS theo tháng (bảng ems_shipping_records).

Dùng cùng logic ngày với trang admin /admin/orders/shipping:
  - Lọc theo created_at (fallback updated_at) quy đổi múi giờ Asia/Ho_Chi_Minh.
  - KHÔNG xóa đơn hàng shop (bảng orders) trừ khi bật --delete-shop-orders.

Chạy trên VPS (SSH vào backend, kích hoạt venv nếu có):

  cd backend
  python scripts/delete_ems_shipping_records_by_month.py --year 2026 --month 5 --dry-run
  python scripts/delete_ems_shipping_records_by_month.py --year 2026 --month 5
  python scripts/delete_ems_shipping_records_by_month.py --year 2026 --month 5 --yes

Tuỳ chọn:
  --delete-import-batches   Xóa luôn lịch sử import EMS (ems_shipping_import_batches) cùng tháng
  --delete-shop-orders      Xóa đơn shop liên kết (order_id) — NGUY HIỂM, cần gõ YES-DELETE-ORDERS
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.order import Order  # noqa: E402
from app.models.order_shipment import (  # noqa: E402
    EmsShippingImportBatch,
    EmsShippingRecord,
)
from app.services.ems_shipment_import import delete_ems_shipping_records  # noqa: E402
from app.services.shipping_operations import _month_bounds, _to_vn_datetime  # noqa: E402

_VN_TZ = timezone(timedelta(hours=7))
_BATCH_SIZE = 500


def _record_import_date(record: EmsShippingRecord) -> date | None:
    local_dt = _to_vn_datetime(record.created_at or record.updated_at)
    return local_dt.date() if local_dt else None


def _in_month(record: EmsShippingRecord, start: date, end: date) -> bool:
    d = _record_import_date(record)
    return d is not None and start <= d <= end


def _fetch_record_ids_postgres(start: date, end: date) -> list[int]:
    """Lọc theo ngày VN trực tiếp trên Postgres — nhanh hơn load toàn bộ."""
    sql = text(
        """
        SELECT id
        FROM ems_shipping_records
        WHERE (
            COALESCE(created_at, updated_at) AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date BETWEEN :start AND :end
        ORDER BY id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start, "end": end}).all()
    return [int(r[0]) for r in rows]


def _fetch_record_ids_python(start: date, end: date) -> list[int]:
    db = SessionLocal()
    try:
        records = db.query(EmsShippingRecord.id, EmsShippingRecord.created_at, EmsShippingRecord.updated_at).all()
        ids: list[int] = []
        for rid, created_at, updated_at in records:
            local_dt = _to_vn_datetime(created_at or updated_at)
            if local_dt is None:
                continue
            d = local_dt.date()
            if start <= d <= end:
                ids.append(int(rid))
        return sorted(ids)
    finally:
        db.close()


def fetch_record_ids(start: date, end: date) -> list[int]:
    if engine.url.drivername.startswith("postgresql"):
        return _fetch_record_ids_postgres(start, end)
    return _fetch_record_ids_python(start, end)


def fetch_sample_records(record_ids: list[int], limit: int = 10) -> list[EmsShippingRecord]:
    if not record_ids:
        return []
    db = SessionLocal()
    try:
        sample_ids = record_ids[:limit]
        return (
            db.query(EmsShippingRecord)
            .filter(EmsShippingRecord.id.in_(sample_ids))
            .order_by(EmsShippingRecord.id)
            .all()
        )
    finally:
        db.close()


def count_import_batches_in_month(start: date, end: date) -> int:
    db = SessionLocal()
    try:
        batches = db.query(EmsShippingImportBatch).all()
        count = 0
        for batch in batches:
            local_dt = _to_vn_datetime(batch.created_at)
            if local_dt and start <= local_dt.date() <= end:
                count += 1
        return count
    finally:
        db.close()


def delete_import_batches_in_month(start: date, end: date) -> int:
    db = SessionLocal()
    try:
        batches = db.query(EmsShippingImportBatch).all()
        to_delete = []
        for batch in batches:
            local_dt = _to_vn_datetime(batch.created_at)
            if local_dt and start <= local_dt.date() <= end:
                to_delete.append(batch.id)
        if not to_delete:
            return 0
        deleted = (
            db.query(EmsShippingImportBatch)
            .filter(EmsShippingImportBatch.id.in_(to_delete))
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted or 0)
    finally:
        db.close()


def linked_order_ids(record_ids: list[int]) -> list[int]:
    if not record_ids:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(EmsShippingRecord.order_id)
            .filter(EmsShippingRecord.id.in_(record_ids))
            .filter(EmsShippingRecord.order_id.isnot(None))
            .distinct()
            .all()
        )
        return sorted({int(r[0]) for r in rows if r[0]})
    finally:
        db.close()


def delete_shop_orders(order_ids: list[int]) -> int:
    if not order_ids:
        return 0
    db = SessionLocal()
    try:
        deleted = 0
        for i in range(0, len(order_ids), _BATCH_SIZE):
            chunk = order_ids[i : i + _BATCH_SIZE]
            n = db.query(Order).filter(Order.id.in_(chunk)).delete(synchronize_session=False)
            deleted += int(n or 0)
        db.commit()
        return deleted
    finally:
        db.close()


def delete_records_in_batches(record_ids: list[int]) -> int:
    total = 0
    db = SessionLocal()
    try:
        for i in range(0, len(record_ids), _BATCH_SIZE):
            chunk = record_ids[i : i + _BATCH_SIZE]
            total += delete_ems_shipping_records(db, chunk)
    finally:
        db.close()
    return total


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xóa bản ghi EMS (ems_shipping_records) theo tháng — giống timeline admin shipping"
    )
    parser.add_argument("--year", type=int, default=2026, help="Năm (mặc định: 2026)")
    parser.add_argument("--month", type=int, default=5, help="Tháng 1-12 (mặc định: 5 = tháng 5)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in thống kê, không xóa")
    parser.add_argument("--yes", action="store_true", help="Bỏ hỏi xác nhận (dùng trên script/CI)")
    parser.add_argument(
        "--delete-import-batches",
        action="store_true",
        help="Xóa luôn ems_shipping_import_batches được tạo trong tháng",
    )
    parser.add_argument(
        "--delete-shop-orders",
        action="store_true",
        help="Xóa đơn shop (orders) liên kết qua order_id — NGUY HIỂM",
    )
    args = parser.parse_args()

    if not 1 <= args.month <= 12:
        print("Tháng phải từ 1 đến 12.")
        return 1
    if args.year < 1970 or args.year > 2100:
        print("Năm không hợp lệ.")
        return 1

    start, end = _month_bounds(args.year, args.month)
    period_label = f"{args.month:02d}/{args.year} ({start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')})"

    db_url = str(engine.url)
    host = (engine.url.host or "").lower()
    is_sqlite = engine.url.drivername.startswith("sqlite")

    print("=" * 60)
    print(f" DATABASE: {db_url}")
    print(f" Kỳ:       {period_label}")
    print(f" Múi giờ:  Asia/Ho_Chi_Minh (created_at / updated_at)")
    print("=" * 60)

    if host and host not in ("", "localhost", "127.0.0.1", "::1") and not is_sqlite:
        print(f" [!] Host DB: {host} — có thể là PRODUCTION. Kiểm tra kỹ trước khi xóa.")

    print("\nĐang đếm bản ghi EMS...")
    record_ids = fetch_record_ids(start, end)
    print(f"  ems_shipping_records: {len(record_ids)} bản ghi")

    if args.delete_import_batches:
        batch_count = count_import_batches_in_month(start, end)
        print(f"  ems_shipping_import_batches (cùng tháng): {batch_count} lần import")

    order_ids: list[int] = []
    if args.delete_shop_orders:
        order_ids = linked_order_ids(record_ids)
        print(f"  orders liên kết (sẽ xóa nếu chạy thật): {len(order_ids)} đơn")

    samples = fetch_sample_records(record_ids, limit=8)
    if samples:
        print("\nMẫu bản ghi (tối đa 8):")
        for r in samples:
            d = _record_import_date(r)
            print(
                f"  id={r.id}  ref={r.reference_code or '-'}  "
                f"order={r.order_code or '-'}  ngày={d.isoformat() if d else '-'}"
            )

    if not record_ids and not (args.delete_import_batches and count_import_batches_in_month(start, end)):
        print("\nKhông có bản ghi nào để xóa.")
        return 0

    print("\nLưu ý: Xóa EMS chỉ gỡ khỏi bảng vận chuyển — đơn shop vẫn còn (trừ --delete-shop-orders).")

    if args.dry_run:
        print("\n-- DRY RUN: không xóa gì. --")
        return 0

    if not args.yes:
        ans = input(f'\nGõ "YES" để xóa {len(record_ids)} bản ghi EMS tháng {args.month:02d}/{args.year}: ').strip()
        if ans != "YES":
            print("Đã hủy.")
            return 1

    if args.delete_shop_orders and order_ids:
        if not args.yes:
            ans2 = input(
                f'\n[!] Sẽ xóa {len(order_ids)} đơn shop. Gõ "YES-DELETE-ORDERS" để tiếp tục: '
            ).strip()
            if ans2 != "YES-DELETE-ORDERS":
                print("Đã hủy (không xóa đơn shop).")
                return 1

    print("\nĐang xóa...")
    deleted_ems = delete_records_in_batches(record_ids)
    print(f"  Đã xóa ems_shipping_records: {deleted_ems}")

    if args.delete_import_batches:
        deleted_batches = delete_import_batches_in_month(start, end)
        print(f"  Đã xóa ems_shipping_import_batches: {deleted_batches}")

    if args.delete_shop_orders and order_ids:
        deleted_orders = delete_shop_orders(order_ids)
        print(f"  Đã xóa orders: {deleted_orders}")

    remaining = len(fetch_record_ids(start, end))
    print(f"\nCòn lại trong tháng {args.month:02d}/{args.year}: {remaining} bản ghi EMS")

    if hasattr(SessionLocal, "remove"):
        SessionLocal.remove()
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
