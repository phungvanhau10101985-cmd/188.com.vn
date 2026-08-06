# backend/scripts/bootstrap_product_ladipages.py
"""
Tạo ladipage 1 SP + sinh nội dung AI cho toàn bộ (hoặc một phần) sản phẩm active.

Khuyến nghị vận hành: bật LADIPAGE_ON_VIEW_ENABLED=true (mặc định) — chỉ sinh khi SP có khách xem.
Script này dùng khi cần bootstrap thủ công / pilot / backfill có chọn lọc.

Mặc định: ảnh chất liệu = gallery SP (không tốn Gemini), DeepSeek text ~30-50₫/SP.

Chạy từ thư mục backend:
  python -m scripts.bootstrap_product_ladipages --dry-run
  python -m scripts.bootstrap_product_ladipages --limit 10 --publish
  python -m scripts.bootstrap_product_ladipages --offset 0 --limit 500 --publish --sleep 0.3
  python -m scripts.bootstrap_product_ladipages --product-id 12345 --publish
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.ladipage_bootstrap import (
    bootstrap_single_product_ladipage,
    product_ids_with_single_ladipage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap ladipage 1 SP cho catalog")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đếm SP cần tạo, không gọi AI")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số SP (0 = không giới hạn)")
    parser.add_argument("--offset", type=int, default=0, help="Bỏ qua N SP đầu trong danh sách candidate")
    parser.add_argument("--product-id", type=int, default=0, help="Chỉ xử lý một products.id")
    parser.add_argument("--publish", action="store_true", help="Publish ngay sau khi sinh xong")
    parser.add_argument("--sleep", type=float, default=0.25, help="Giây nghỉ giữa mỗi SP")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Tạo cả SP đã có ladipage 1 SP (mặc định: bỏ qua)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.product_id:
            product = db.query(Product).filter(Product.id == args.product_id, Product.is_active.is_(True)).first()
            if not product:
                print(f"Không tìm thấy SP active id={args.product_id}")
                return 1
            candidates = [product]
        else:
            covered = product_ids_with_single_ladipage(db) if not args.include_existing else set()
            q = db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.id.asc())
            if args.offset:
                q = q.offset(args.offset)
            if args.limit:
                q = q.limit(args.limit)
            products = q.all()
            candidates = [p for p in products if args.include_existing or p.id not in covered]

        total = len(candidates)
        est_vnd = total * 40
        print(f"Candidate: {total} sản phẩm (~{est_vnd:,}₫ DeepSeek text @ 40₫/SP, ảnh SP = 0₫)".replace(",", "."))
        if args.dry_run:
            for p in candidates[:20]:
                print(f"  - id={p.id} {(p.name or '')[:60]}")
            if total > 20:
                print(f"  ... và {total - 20} SP nữa")
            return 0

        ok = 0
        skipped = 0
        failed = 0
        for i, product in enumerate(candidates, start=1):
            name_preview = (product.name or "")[:50]
            print(f"[{i}/{total}] id={product.id} {name_preview!r} …", flush=True)
            try:
                lp = bootstrap_single_product_ladipage(
                    db,
                    product,
                    publish=args.publish,
                    skip_if_exists=not args.include_existing,
                )
                if lp is None:
                    skipped += 1
                    print("  → bỏ qua (đã có ladipage)")
                else:
                    ok += 1
                    print(f"  → ladipage id={lp.id} slug={lp.slug} status={lp.status}")
            except Exception as exc:
                failed += 1
                db.rollback()
                print(f"  → LỖI: {exc}")
            if args.sleep > 0 and i < total:
                time.sleep(args.sleep)

        print(f"Xong: ok={ok} skip={skipped} fail={failed}")
        return 0 if failed == 0 else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
