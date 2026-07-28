#!/usr/bin/env python3
"""
Xóa sản phẩm không có ảnh đại diện / thumbnail hợp lệ.

Ảnh hợp lệ được kiểm tra trong main_image, images, gallery, colors[].img
(cùng logic storefront: product_has_storefront_image).

Trước khi xóa, script thử gán main_image từ gallery/colors nếu có thể.

Chạy thử (chỉ liệt kê):
  cd backend
  python scripts/delete_products_without_storefront_image.py

Xóa thật:
  python scripts/delete_products_without_storefront_image.py --execute

Chỉ SP đang active trên web:
  python scripts/delete_products_without_storefront_image.py --active-only --execute

SP bị chặn xóa (kho thanh lý): gỡ khỏi web thay vì xóa DB:
  python scripts/delete_products_without_storefront_image.py --execute --deactivate-if-blocked
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crud.product import bulk_delete_products_by_db_ids  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services import warehouse_clearance as wh_clearance_svc  # noqa: E402
from app.services.product_image_visibility import (  # noqa: E402
    product_has_storefront_image,
    repair_main_image_from_candidates,
)


def _chunked(ids: List[int], size: int) -> List[List[int]]:
    if size <= 0:
        return [ids]
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def _scan_products(
    db,
    *,
    active_only: bool,
    parents_only: bool,
    limit: int,
) -> List[Product]:
    q = db.query(Product).order_by(Product.id.asc())
    if active_only:
        q = q.filter(Product.is_active.is_(True))
    if parents_only:
        q = q.filter(
            (Product.is_warehouse_clearance.is_(False))
            | (Product.is_warehouse_clearance.is_(None))
        )
    if limit > 0:
        q = q.limit(limit)
    return q.all()


def _partition_for_cleanup(
    rows: List[Product],
    *,
    do_repair: bool,
) -> Tuple[List[Product], List[Product], List[Product]]:
    """
    Trả (repaired, delete_candidates, already_ok).
    repaired: đã sửa main_image từ gallery/colors (chỉ khi do_repair=True).
    """
    repaired: List[Product] = []
    delete_candidates: List[Product] = []
    already_ok: List[Product] = []

    for row in rows:
        if product_has_storefront_image(row):
            already_ok.append(row)
            continue

        if do_repair and repair_main_image_from_candidates(row):
            if product_has_storefront_image(row):
                repaired.append(row)
                continue

        delete_candidates.append(row)

    return repaired, delete_candidates, already_ok


def _print_sample(rows: List[Product], *, label: str, max_rows: int) -> None:
    if not rows:
        return
    print(f"\n{label} ({len(rows)}):")
    for row in rows[:max_rows]:
        print(
            f"  id={row.id} product_id={row.product_id} "
            f"active={row.is_active} main_image={repr((row.main_image or '')[:60])}"
        )
    if len(rows) > max_rows:
        print(f"  ... và {len(rows) - max_rows} SP khác")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xóa SP không có ảnh đại diện/thumbnail hợp lệ."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Thực hiện sửa main_image + xóa DB (mặc định: dry-run).",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Chỉ quét SP is_active=True.",
    )
    parser.add_argument(
        "--parents-only",
        action="store_true",
        help="Bỏ qua SP kho thanh lý (is_warehouse_clearance).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Giới hạn số SP quét (0 = không giới hạn).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Số SP xóa mỗi lần commit (mặc định 200).",
    )
    parser.add_argument(
        "--deactivate-if-blocked",
        action="store_true",
        help="SP không xóa được do kho: gỡ khỏi web (is_active=False).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=30,
        help="Số dòng mẫu in ra (mặc định 30).",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = _scan_products(
            db,
            active_only=args.active_only,
            parents_only=args.parents_only,
            limit=args.limit,
        )
        print(
            f"Đã quét {len(rows)} SP | dry-run={not args.execute} | "
            f"active_only={args.active_only} | parents_only={args.parents_only}"
        )

        repaired, delete_candidates, already_ok = _partition_for_cleanup(
            rows,
            do_repair=args.execute,
        )

        if args.execute and repaired:
            db.commit()
            print(f"\nĐã sửa main_image cho {len(repaired)} SP từ gallery/colors.")

        _print_sample(repaired, label="Sẽ giữ (đã sửa main_image)", max_rows=args.sample)
        _print_sample(delete_candidates, label="Sẽ xóa (không có ảnh hợp lệ)", max_rows=args.sample)

        print(
            f"\nTổng kết: ok={len(already_ok)} | "
            f"sửa={len(repaired)} | xóa={len(delete_candidates)}"
        )

        if not args.execute:
            print("\nChạy lại với --execute để sửa main_image và xóa thật.")
            return 0

        if not delete_candidates:
            return 0

        to_delete_ids: List[int] = []
        to_deactivate: List[Product] = []
        blocked: List[Tuple[int, str]] = []

        for row in delete_candidates:
            try:
                wh_clearance_svc.assert_product_deletion_allowed(db, row)
                to_delete_ids.append(int(row.id))
            except ValueError as exc:
                if args.deactivate_if_blocked:
                    to_deactivate.append(row)
                else:
                    blocked.append((int(row.id), str(exc)))

        deleted_total = 0
        for chunk in _chunked(to_delete_ids, args.batch_size):
            deleted, not_found = bulk_delete_products_by_db_ids(db, chunk)
            deleted_total += len(deleted)
            if not_found:
                print(f"Cảnh báo: không tìm thấy ids {not_found[:10]}")

        deactivated = 0
        if to_deactivate:
            for row in to_deactivate:
                if row.is_active:
                    row.is_active = False
                    deactivated += 1
            if deactivated:
                db.commit()

        print(f"\nĐã xóa: {deleted_total} SP.")
        if deactivated:
            print(f"Đã gỡ khỏi web (không xóa DB): {deactivated} SP.")
        if blocked:
            print(f"Bị chặn xóa (chạy --deactivate-if-blocked để gỡ web): {len(blocked)}")
            for pk, msg in blocked[:10]:
                print(f"  id={pk}: {msg[:120]}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
