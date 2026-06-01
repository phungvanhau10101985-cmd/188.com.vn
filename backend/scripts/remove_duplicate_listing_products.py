#!/usr/bin/env python3
"""
Xóa sản phẩm trùng mã nguồn (cột A / id 1688–Taobao).

Hai SP cùng prefix trước «a188» (vd A990013135592a188K8790 và …a188F6946) được coi là trùng offer.
Giữ một bản (ưu tiên: còn hàng → lượt mua cao → id nhỏ hơn), xóa các bản còn lại.

Chạy thử (không xóa):
  cd backend
  python scripts/remove_duplicate_listing_products.py

Xóa thật:
  python scripts/remove_duplicate_listing_products.py --execute

Chỉ in nhóm có prefix cụ thể:
  python scripts/remove_duplicate_listing_products.py --prefix A990013135592

Xóa trùng đúng chuỗi product_id (hiếm):
  python scripts/remove_duplicate_listing_products.py --by-exact-product-id --execute
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.crud.product import (  # noqa: E402
    _listing_source_prefix_from_product_id,
    bulk_delete_products_by_db_ids,
)
from app.db.session import SessionLocal
from app.models.product import Product


def _keeper_sort_key(p: Product) -> Tuple[int, int, int]:
    """Giữ bản «tốt nhất»; xóa các bản còn lại."""
    return (
        1 if int(p.available or 0) > 0 else 0,
        int(p.purchases or 0),
        -int(p.id or 0),
    )


def group_by_listing_prefix(
    products: List[Product],
    *,
    prefix_filter: Optional[str] = None,
) -> Dict[str, List[Product]]:
    groups: Dict[str, List[Product]] = defaultdict(list)
    pf = (prefix_filter or "").strip().casefold()
    for p in products:
        pid = (p.product_id or "").strip()
        if not pid:
            continue
        src = _listing_source_prefix_from_product_id(pid)
        if not src:
            continue
        pk = src["prefix_key"]
        if pf and pk != pf:
            continue
        groups[pk].append(p)
    return {k: v for k, v in groups.items() if len(v) > 1}


def group_by_exact_product_id(products: List[Product]) -> Dict[str, List[Product]]:
    groups: Dict[str, List[Product]] = defaultdict(list)
    for p in products:
        pid = (p.product_id or "").strip()
        if not pid:
            continue
        groups[pid.casefold()].append(p)
    return {k: v for k, v in groups.items() if len(v) > 1}


def pick_keeper_and_duplicates(group: List[Product]) -> Tuple[Product, List[Product]]:
    ordered = sorted(group, key=_keeper_sort_key, reverse=True)
    keeper = ordered[0]
    dups = ordered[1:]
    return keeper, dups


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Xóa SP trùng mã cột A (prefix listing 1688/Taobao)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Thực hiện xóa DB (mặc định: chỉ liệt kê — dry-run).",
    )
    parser.add_argument(
        "--prefix",
        metavar="A990013135592",
        help="Chỉ xử lý nhóm có prefix này (không phân biệt hoa thường).",
    )
    parser.add_argument(
        "--by-exact-product-id",
        action="store_true",
        help="Nhóm theo product_id giống hệt (thay vì prefix cột A).",
    )
    parser.add_argument(
        "--limit-groups",
        type=int,
        default=0,
        help="Giới hạn số nhóm trùng xử lý (0 = không giới hạn).",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(Product)
            .filter(Product.product_id.isnot(None), Product.product_id != "")
            .order_by(Product.id.asc())
            .all()
        )
        if args.by_exact_product_id:
            groups = group_by_exact_product_id(rows)
            mode = "exact product_id"
        else:
            groups = group_by_listing_prefix(rows, prefix_filter=args.prefix)
            mode = "listing prefix (cột A)"

        if not groups:
            print(f"Không có nhóm trùng theo {mode}.")
            return 0

        keys = sorted(groups.keys())
        if args.limit_groups and args.limit_groups > 0:
            keys = keys[: args.limit_groups]

        to_delete_ids: List[int] = []
        print(f"Chế độ: {mode} | nhóm trùng: {len(keys)} | dry-run: {not args.execute}\n")

        for key in keys:
            group = groups[key]
            keeper, dups = pick_keeper_and_duplicates(group)
            sample_prefix = _listing_source_prefix_from_product_id(keeper.product_id or "")
            label = (sample_prefix or {}).get("prefix") or keeper.product_id or key
            print(f"=== {label} ({len(group)} SP) — giữ id={keeper.id} product_id={keeper.product_id}")
            print(
                f"    available={keeper.available} purchases={keeper.purchases} slug={keeper.slug}"
            )
            for d in dups:
                print(
                    f"    XÓA id={d.id} product_id={d.product_id} "
                    f"available={d.available} purchases={d.purchases}"
                )
                to_delete_ids.append(int(d.id))
            print()

        print(f"Tổng sẽ xóa: {len(to_delete_ids)} sản phẩm.")

        if not args.execute:
            print("\nChạy lại với --execute để xóa thật.")
            return 0

        if not to_delete_ids:
            return 0

        deleted, not_found = bulk_delete_products_by_db_ids(db, to_delete_ids)
        print(f"\nĐã xóa: {len(deleted)} | không tìm thấy: {len(not_found)}")
        if not_found:
            print("  not_found ids:", not_found[:20])
        return 0 if not not_found else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
