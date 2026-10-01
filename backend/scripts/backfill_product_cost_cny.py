"""Đổ giá gốc tệ từ số đã cào (pro_lower_price) cho hàng Trung Quốc.

Mặc định chỉ in số dòng, không ghi database. Thêm --apply để ghi những ô cost_cny đang trống.

    cd backend
    python scripts/backfill_product_cost_cny.py
    python scripts/backfill_product_cost_cny.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.product_import_cost import (
    import_cost_is_set,
    looks_like_china_source,
    scraped_cny_amount,
)


def _source_key(product_id: str | None) -> str | None:
    """Mã nguồn trước hậu tố nội bộ a188 (draft lưu A…, sản phẩm lưu A…a188SKU)."""
    raw = (product_id or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    idx = lower.find("a188")
    head = raw[:idx] if idx > 0 else raw
    head = head.upper()
    if len(head) < 8:
        return None
    return head


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ghi cost_cny. Không có cờ này thì chỉ thống kê.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        draft_rows = db.execute(
            text(
                """
                SELECT
                    coalesce(
                        nullif(btrim(published_product_id), ''),
                        nullif(btrim(product_data->>'product_id'), '')
                    ) AS pid,
                    product_data->>'pro_lower_price' AS raw_cny,
                    id
                FROM product_import_drafts
                WHERE btrim(coalesce(product_data->>'pro_lower_price', '')) <> ''
                """
            )
        ).fetchall()
        draft_cny: dict[str, tuple[int, str]] = {}
        for pid, raw, draft_id in draft_rows:
            key = _source_key(str(pid) if pid else None)
            if not key or raw is None:
                continue
            prev = draft_cny.get(key)
            if prev is None or int(draft_id) > prev[0]:
                draft_cny[key] = (int(draft_id), str(raw))

        rows = db.query(
            Product.id,
            Product.product_id,
            Product.origin,
            Product.link_default,
            Product.pro_lower_price,
            Product.cost_cny,
            Product.cost_vnd,
        ).all()

        already = 0
        has_vnd = 0
        not_china = 0
        not_numeric = 0
        ready: list[tuple[int, float]] = []
        for row in rows:
            if import_cost_is_set(row.cost_cny):
                already += 1
                continue
            if import_cost_is_set(row.cost_vnd):
                has_vnd += 1
                continue
            key = _source_key(row.product_id)
            draft_raw = draft_cny.get(key)[1] if key and key in draft_cny else None
            from_product = scraped_cny_amount(row.pro_lower_price)
            from_draft = scraped_cny_amount(draft_raw)
            china = looks_like_china_source(row.origin, row.link_default) or (
                str(row.product_id or "").upper().startswith("A")
                or str(row.product_id or "").upper().startswith("T")
            )
            if from_product is not None and china:
                amount = from_product
            elif from_draft is not None and china:
                amount = from_draft
            elif not china and from_draft is None:
                not_china += 1
                continue
            else:
                not_numeric += 1
                continue
            ready.append((row.id, amount))

        print(f"Tong san pham: {len(rows)}")
        print(f"Draft co gia te (theo ma nguon): {len(draft_cny)}")
        print(f"Da co cost_cny: {already}")
        print(f"Da co gia Viet Nam: {has_vnd}")
        print(f"Khong nhan nguon Trung Quoc: {not_china}")
        print(f"Khong co so te (san pham va draft): {not_numeric}")
        print(f"Se ghi cost_cny: {len(ready)}")
        if not args.apply:
            print("Chua ghi. Chay lai voi --apply de cap nhat.")
            return

        for product_id, amount in ready:
            db.query(Product).filter(Product.id == product_id).update(
                {Product.cost_cny: amount},
                synchronize_session=False,
            )
        db.commit()
        print(f"Da ghi {len(ready)} dong.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
