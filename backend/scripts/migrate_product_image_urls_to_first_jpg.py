"""
Chuẩn hoá lại URL ảnh sản phẩm trong DB: cắt tại cụm .jpg đầu tiên.

Ví dụ:
  .../O1CN01...-cib.jpg_800x800q90.jpg  →  .../O1CN01...-cib.jpg

Cập nhật bảng:
  - products (main_image, images, gallery, colors, product_info, description)
  - product_import_drafts (product_data) — tùy chọn --include-drafts

DATABASE_URL trong backend/.env (hoặc biến môi trường).

  cd /var/www/188.com.vn/backend
  source .venv/bin/activate
  python scripts/migrate_product_image_urls_to_first_jpg.py --audit
  python scripts/migrate_product_image_urls_to_first_jpg.py --dry-run
  python scripts/migrate_product_image_urls_to_first_jpg.py --yes
  python scripts/migrate_product_image_urls_to_first_jpg.py --yes --include-drafts
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
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.product_import_draft import ProductImportDraft  # noqa: E402
from app.services.alicdn_urls import (  # noqa: E402
    iter_bad_image_urls_in_record,
    normalize_product_image_record,
)


def _record_json_sig(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)


def _sql_fix_main_image_column(db: Session, *, dry_run: bool) -> Dict[str, int]:
    """Sửa nhanh cột main_image (varchar) — pattern …cib.jpg_800x800q90.jpg."""
    count = int(
        db.execute(
            text(
                """
                SELECT count(*) FROM products
                WHERE main_image IS NOT NULL AND main_image ~* '\\.jpg_'
                """
            )
        ).scalar()
        or 0
    )
    if not dry_run and count > 0:
        db.execute(
            text(
                """
                UPDATE products
                SET main_image = regexp_replace(main_image, '(?i)(\\.jpg)_.*$', '\\1')
                WHERE main_image IS NOT NULL AND main_image ~* '\\.jpg_'
                """
            )
        )
        db.commit()
    return {"main_image_sql_fixed": count}


def _product_image_fields(product: Product) -> Dict[str, Any]:
    return {
        "main_image": product.main_image,
        "images": product.images if isinstance(product.images, list) else [],
        "gallery": product.gallery if isinstance(product.gallery, list) else [],
        "colors": product.colors if isinstance(product.colors, list) else [],
        "product_info": product.product_info,
        "description": product.description,
    }


def _apply_product_image_fields(product: Product, normalized: Dict[str, Any]) -> None:
    product.main_image = normalized.get("main_image")
    product.images = normalized.get("images") or []
    product.gallery = normalized.get("gallery") or []
    product.colors = normalized.get("colors") or []
    product.product_info = normalized.get("product_info")
    product.description = normalized.get("description")
    flag_modified(product, "images")
    flag_modified(product, "gallery")
    flag_modified(product, "colors")
    flag_modified(product, "product_info")


def _collect_change_samples(
    before: Dict[str, Any],
    after: Dict[str, Any],
    *,
    label: str,
    samples: List[Dict[str, str]],
    max_samples: int = 8,
) -> None:
    if len(samples) >= max_samples:
        return

    def walk(path: str, b: Any, a: Any) -> None:
        nonlocal samples
        if len(samples) >= max_samples:
            return
        if isinstance(b, str) and isinstance(a, str) and b != a and _looks_changed_url(b, a):
            samples.append(
                {
                    "id": label,
                    "field": path,
                    "before": b[:220],
                    "after": a[:220],
                }
            )
            return
        if isinstance(b, list) and isinstance(a, list):
            for idx, (bi, ai) in enumerate(zip(b, a)):
                walk(f"{path}[{idx}]", bi, ai)
            return
        if isinstance(b, dict) and isinstance(a, dict):
            for key in b.keys():
                if key in a:
                    walk(f"{path}.{key}" if path else str(key), b.get(key), a.get(key))

    walk("", before, after)


def _looks_changed_url(before: str, after: str) -> bool:
    return bool(before.strip() and after.strip() and before.strip() != after.strip())


def audit_products(db: Session, *, limit: Optional[int]) -> Dict[str, Any]:
    scanned = 0
    bad_records = 0
    bad_urls = 0
    samples: List[str] = []

    q = db.query(Product.id, Product.product_id, Product.main_image, Product.images, Product.gallery, Product.colors, Product.product_info, Product.description).order_by(Product.id.asc())
    if limit is not None:
        q = q.limit(limit)

    for row in q.yield_per(200):
        scanned += 1
        payload = {
            "main_image": row.main_image,
            "images": row.images if isinstance(row.images, list) else [],
            "gallery": row.gallery if isinstance(row.gallery, list) else [],
            "colors": row.colors if isinstance(row.colors, list) else [],
            "product_info": row.product_info,
            "description": row.description,
        }
        hits = list(iter_bad_image_urls_in_record(payload))
        if not hits:
            continue
        bad_records += 1
        bad_urls += len(hits)
        if len(samples) < 10:
            samples.append(f"{row.product_id}: {hits[0][:220]}")

    return {
        "table": "products",
        "scanned": scanned,
        "bad_records": bad_records,
        "bad_urls": bad_urls,
        "samples": samples,
    }


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

    last_id = 0
    while True:
        q = db.query(Product).filter(Product.id > last_id).order_by(Product.id.asc())
        if limit is not None:
            remaining = limit - scanned
            if remaining <= 0:
                break
            q = q.limit(min(batch_size, remaining))
        else:
            q = q.limit(batch_size)

        rows: List[Product] = q.all()
        if not rows:
            break

        pending: List[Tuple[Product, Dict[str, Any]]] = []

        for product in rows:
            scanned += 1
            last_id = product.id
            before = _product_image_fields(product)
            after = normalize_product_image_record(before)
            if _record_json_sig(before) == _record_json_sig(after):
                continue

            changed += 1
            _collect_change_samples(before, after, label=str(product.product_id), samples=samples)

            if dry_run:
                continue
            pending.append((product, after))

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

    last_id = 0
    while True:
        q = (
            db.query(ProductImportDraft)
            .filter(ProductImportDraft.id > last_id, ProductImportDraft.product_data.isnot(None))
            .order_by(ProductImportDraft.id.asc())
        )
        if limit is not None:
            remaining = limit - scanned
            if remaining <= 0:
                break
            q = q.limit(min(batch_size, remaining))
        else:
            q = q.limit(batch_size)

        rows: List[ProductImportDraft] = q.all()
        if not rows:
            break

        pending: List[Tuple[ProductImportDraft, Dict[str, Any]]] = []

        for draft in rows:
            scanned += 1
            last_id = draft.id
            raw = draft.product_data
            if not isinstance(raw, dict):
                continue

            before = copy.deepcopy(raw)
            after = normalize_product_image_record(before)
            if _record_json_sig(before) == _record_json_sig(after):
                continue

            changed += 1
            _collect_change_samples(
                before,
                after,
                label=f"draft:{draft.id}",
                samples=samples,
            )

            if dry_run:
                continue
            pending.append((draft, after))

        if not dry_run and pending:
            for row, normalized in pending:
                row.product_data = normalized
                flag_modified(row, "product_data")
            db.commit()

    return {
        "table": "product_import_drafts",
        "scanned": scanned,
        "changed": changed,
        "samples": samples,
    }


def _print_summary(results: List[Dict[str, Any]], *, dry_run: bool, audit: bool = False) -> None:
    print("\nKết quả:")
    for row in results:
        if audit:
            print(
                f"  {row['table']:<24} scanned={row['scanned']:<6} "
                f"bad_records={row.get('bad_records', 0):<6} bad_urls={row.get('bad_urls', 0)}"
            )
            for sample in row.get("samples") or []:
                print(f"    {sample}")
            continue

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
    parser.add_argument("--audit", action="store_true", help="Chỉ đếm URL còn .jpg_... chưa sửa")
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
        if args.audit:
            results = [audit_products(db, limit=args.limit)]
            _print_summary(results, dry_run=True, audit=True)
            sql_left = db.execute(
                text(
                    """
                    SELECT count(*) FROM products
                    WHERE (main_image IS NOT NULL AND main_image ~* '\\.jpg_')
                       OR (images::text ~* '\\.jpg_')
                       OR (gallery::text ~* '\\.jpg_')
                       OR (colors::text ~* '\\.jpg_')
                    """
                )
            ).scalar()
            print(f"\nSQL rows still matching '.jpg_': {sql_left}")
            print("\n--audit: không ghi DB.--")
            return 0

        sql_preview = _sql_fix_main_image_column(db, dry_run=True)
        print(f"main_image SQL có thể sửa: {sql_preview['main_image_sql_fixed']}")

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
        sql_done = _sql_fix_main_image_column(db_run, dry_run=False)
        print(f"main_image SQL đã sửa: {sql_done['main_image_sql_fixed']}")
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

    db_audit = SessionLocal()
    try:
        audit_results = [audit_products(db_audit, limit=args.limit)]
    finally:
        db_audit.close()
        engine.dispose()
    _print_summary(audit_results, dry_run=False, audit=True)

    print("\nXong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
