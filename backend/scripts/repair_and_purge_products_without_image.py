#!/usr/bin/env python3
"""
Sửa main_image từ gallery/colors và xóa SP không có ảnh đại diện hợp lệ.

Chạy thử:
  cd backend
  python scripts/repair_and_purge_products_without_image.py

Thực hiện:
  python scripts/repair_and_purge_products_without_image.py --execute
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crud.product import bulk_delete_products_by_db_ids  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services import warehouse_clearance as wh_clearance_svc  # noqa: E402
from app.services.product_image_visibility import (  # noqa: E402
    product_has_storefront_image,
    repair_main_image_from_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Ghi DB / xóa thật")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--deactivate-if-blocked",
        action="store_true",
        help="SP không xóa được do kho → gỡ khỏi web",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(Product)
            .filter(
                (Product.is_warehouse_clearance.is_(False))
                | (Product.is_warehouse_clearance.is_(None))
            )
            .order_by(Product.id.asc())
            .all()
        )

        to_repair: List[Product] = []
        to_delete: List[Product] = []

        for row in rows:
            if product_has_storefront_image(row):
                if repair_main_image_from_candidates(row):
                    to_repair.append(row)
                continue
            to_delete.append(row)

        print(f"Quét {len(rows)} SP | sửa main_image: {len(to_repair)} | xóa: {len(to_delete)}")

        for row in to_repair[:10]:
            print(f"  SỬA id={row.id} pid={row.product_id} → {row.main_image[:70]}...")
        if len(to_repair) > 10:
            print(f"  ... và {len(to_repair) - 10} SP khác")

        for row in to_delete[:10]:
            print(f"  XÓA id={row.id} pid={row.product_id} active={row.is_active}")
        if len(to_delete) > 10:
            print(f"  ... và {len(to_delete) - 10} SP khác")

        if not args.execute:
            print("\nChạy lại với --execute để áp dụng.")
            return 0

        if to_repair:
            db.commit()
            print(f"\nĐã sửa main_image: {len(to_repair)} SP.")

        delete_ids: List[int] = []
        deactivate_rows: List[Product] = []
        blocked = 0

        for row in to_delete:
            try:
                wh_clearance_svc.assert_product_deletion_allowed(db, row)
                delete_ids.append(int(row.id))
            except ValueError:
                if args.deactivate_if_blocked:
                    deactivate_rows.append(row)
                else:
                    blocked += 1

        deleted_total = 0
        for i in range(0, len(delete_ids), args.batch_size):
            chunk = delete_ids[i : i + args.batch_size]
            deleted, _ = bulk_delete_products_by_db_ids(db, chunk)
            deleted_total += len(deleted)

        deactivated = 0
        for row in deactivate_rows:
            if row.is_active:
                row.is_active = False
                deactivated += 1
        if deactivated:
            db.commit()

        print(f"Đã xóa: {deleted_total} SP.")
        if deactivated:
            print(f"Đã gỡ khỏi web: {deactivated} SP.")
        if blocked:
            print(f"Bị chặn xóa: {blocked} SP (dùng --deactivate-if-blocked).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
