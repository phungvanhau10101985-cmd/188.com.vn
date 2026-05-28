"""
Chuẩn hoá lại URL ảnh sản phẩm trong DB: cắt tại cụm .jpg đầu tiên.

Ví dụ:
  .../O1CN01...-cib.jpg_800x800q90.jpg  →  .../O1CN01...-cib.jpg

Cập nhật bảng:
  - products (main_image, images, gallery, colors)
  - product_import_drafts (product_data) — tùy chọn --include-drafts

DATABASE_URL trong backend/.env (hoặc biến môi trường).

  cd backend
  python scripts/migrate_product_image_urls_to_first_jpg.py --dry-run
  python scripts/migrate_product_image_urls_to_first_jpg.py --yes
  python scripts/migrate_product_image_urls_to_first_jpg.py --yes --include-drafts
  python scripts/migrate_product_image_urls_to_first_jpg.py --yes --limit 50
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_import_draft import ProductImportDraft  # noqa: E402
from app.services.alicdn_urls import normalize_excel_product_image_urls  # noqa: E402


def _product_image_fields(product: Product) -> Dict[str, Any]:
    return {
        "main_image": product.main_image,
        "images": product.images if isinstance(product.images, list) else [],
        "gallery": product.gallery if isinstance(product.gallery, list) else [],
        "colors": product.colors if isinstance(product.colors, list) else [],
    }


def _normalize_image_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(data)
    normalize_excel_product_image_urls(out)
    return out


def _fields_changed(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    return before != after


def _apply_product_image_fields(product: Product, normalized: Dict[str, Any]) -> None:
    product.main_image = normalized.get("main_image")
    product.images = normalized.get("images") or []
    product.gallery = normalized.get("gallery") or []
    product.colors = normalized.get("colors") or []


def migrate_products(
    db: Session,
    *,
    dry_run: bool,
    batch_size: int,
    limit: Optional[int],
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    samples: List[Dict[str, str]] = []

    q = db.query(Product).order_by(Product.id.asc())
    if limit is not None:
        q = q.limit(limit)

    pending: List[Tuple[Product, Dict[str, Any]]] = []

    for product in q.yield_per(max(50, batch_size)):
        scanned += 1
        before = _product_image_fields(product)
        after = _normalize_image_fields(before)
        if not _fields_changed(before, after):
            continue

        changed += 1
        if len(samples) < 8:
            samples.append(
                {
                    "product_id": str(product.product_id),
                    "main_image_before": str(before.get("main_image") or "")[:180],
                    "main_image_after": str(after.get("main_image") or "")[:180],
                }
            )

        if dry_run:
            continue

        pending.append((product, after))
        if len(pending) >= batch_size:
            for row, normalized in pending:
                _apply_product_image_fields(row, normalized)
            db.commit()
            pending.clear()

    if not dry_run and pending:
        for row, normalized in pending:
            _apply_product_image_fields(row, normalized)
        db.commit()

    return {
        "table": "products",
        "scanned": scanned,
        "changed": changed,
        "samples": samples,
    }


def migrate_import_drafts(
    db: Session,
    *,
    dry_run: bool,
    batch_size: int,
    limit: Optional[int],
) -> Dict[str, Any]:
    scanned = 0
    changed = 0
    samples: List[Dict[str, str]] = []

    q = (
        db.query(ProductImportDraft)
        .filter(ProductImportDraft.product_data.isnot(None))
        .order_by(ProductImportDraft.id.asc())
    )
    if limit is not None:
        q = q.limit(limit)

    pending: List[Tuple[ProductImportDraft, Dict[str, Any]]] = []

    for draft in q.yield_per(max(50, batch_size)):
        scanned += 1
        raw = draft.product_data
        if not isinstance(raw, dict):
            continue

        before = copy.deepcopy(raw)
        after = copy.deepcopy(raw)
        normalize_excel_product_image_urls(after)
        if before == after:
            continue

        changed += 1
        if len(samples) < 8:
            samples.append(
                {
                    "draft_id": str(draft.id),
                    "main_image_before": str(before.get("main_image") or "")[:180],
                    "main_image_after": str(after.get("main_image") or "")[:180],
                }
            )

        if dry_run:
            continue

        pending.append((draft, after))
        if len(pending) >= batch_size:
            for row, normalized in pending:
                row.product_data = normalized
            db.commit()
            pending.clear()

    if not dry_run and pending:
        for row, normalized in pending:
            row.product_data = normalized
        db.commit()

    return {
        "table": "product_import_drafts",
        "scanned": scanned,
        "changed": changed,
        "samples": samples,
    }


def _print_summary(results: List[Dict[str, Any]], *, dry_run: bool) -> None:
    print("\nKết quả:")
    for row in results:
        print(
            f"  {row['table']:<24} scanned={row['scanned']:<6} "
            f"changed={row['changed']:<6} dry_run={dry_run}"
        )
        for sample in row.get("samples") or []:
            print(f"    sample: {json.dumps(sample, ensure_ascii=False)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chuẩn hoá URL ảnh SP trong DB — cắt tại .jpg đầu tiên",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ đếm/thống kê, không ghi DB")
    parser.add_argument("--yes", action="store_true", help="Bỏ hỏi xác nhận trước khi ghi DB")
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Cập nhật thêm product_import_drafts.product_data",
    )
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số bản ghi mỗi bảng (test)")
    parser.add_argument("--batch-size", type=int, default=200, help="Commit mỗi N bản ghi (mặc định 200)")
    args = parser.parse_args()

    batch_size = max(1, min(int(args.batch_size or 200), 2000))

    db_url = str(engine.url)
    pwd = engine.url.password
    safe_url = db_url.replace(str(pwd), "***") if pwd else db_url
    print("=" * 72)
    print(f" DATABASE: {safe_url}")
    print(f" Driver:   {engine.url.drivername}")
    print("=" * 72)

    db = SessionLocal()
    try:
        results = [migrate_products(db, dry_run=True, batch_size=batch_size, limit=args.limit)]
        if args.include_drafts:
            results.append(
                migrate_import_drafts(db, dry_run=True, batch_size=batch_size, limit=args.limit)
            )
    finally:
        db.close()
        engine.dispose()

    _print_summary(results, dry_run=True)

    if args.dry_run:
        print("\n--dry-run: không ghi DB.--")
        return 0

    total_changed = sum(int(r.get("changed") or 0) for r in results)
    if total_changed == 0:
        print("\nKhông có bản ghi cần sửa.")
        return 0

    if not args.yes:
        ans = input(f'\nSẽ sửa {total_changed} bản ghi. Gõ "YES" để ghi DB (Enter = hủy): ').strip()
        if ans != "YES":
            print("Đã hủy.")
            return 1

    db_run = SessionLocal()
    try:
        final_results = [
            migrate_products(db_run, dry_run=False, batch_size=batch_size, limit=args.limit)
        ]
        if args.include_drafts:
            final_results.append(
                migrate_import_drafts(db_run, dry_run=False, batch_size=batch_size, limit=args.limit)
            )
    finally:
        db_run.close()
        engine.dispose()

    _print_summary(final_results, dry_run=False)
    print("\nXong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
