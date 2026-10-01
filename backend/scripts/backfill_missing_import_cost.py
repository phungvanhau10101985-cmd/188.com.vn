"""Đổ giá nhập cho sản phẩm chưa có giá gốc tệ (cost_cny).

- Hàng sale thanh lý kho: hàng Việt Nam, ghi giá nhập cost_vnd = 0. Không ghi giá tệ.
- Hàng còn lại chưa có giá nhập: đảo giá bán VNĐ về cost_cny theo cùng lưới và tỷ giá
  dùng khi tính lợi nhuận (giá bán ≈ CN¥ × hệ số × tỷ giá, làm tròn lên 10.000đ).

Mỗi sản phẩm chỉ được một trong hai cột. Dòng đã có cost_cny hoặc cost_vnd thì bỏ qua.

Mặc định chỉ in số dòng, không ghi database. Thêm --apply để ghi.

    cd backend
    python scripts/backfill_missing_import_cost.py
    python scripts/backfill_missing_import_cost.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, update

from app.db.session import SessionLocal
from app.models.ad_spend import AdSpendSettings
from app.models.product import Product
from app.services.ad_spend_profit import default_listing_rate
from app.services.listing_cny_grid import listing_vnd_to_cny
from app.services.product_import_cost import import_cost_is_set

_BATCH = 1000


def profit_listing_rate(db) -> float:
    """Cùng nguồn tỷ giá trang lợi nhuận: mức đã lưu, không có thì tỷ giá cào catalog."""
    row = db.query(AdSpendSettings.vnd_per_cny).filter(AdSpendSettings.id == 1).one_or_none()
    saved = None if row is None else row[0]
    try:
        rate = float(saved) if saved is not None else 0.0
    except (TypeError, ValueError):
        rate = 0.0
    if rate > 0:
        return rate
    return float(default_listing_rate())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Ghi database. Không có cờ này thì chỉ thống kê.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rate = profit_listing_rate(db)
        rows = db.query(
            Product.id,
            Product.product_id,
            Product.price,
            Product.cost_cny,
            Product.cost_vnd,
            Product.is_warehouse_clearance,
        ).all()

        already_cny = 0
        already_vnd = 0
        warehouse_zero: list[int] = []
        inverted: list[tuple[int, float]] = []
        no_price = 0
        invert_failed = 0
        samples_wh: list[str] = []
        samples_cny: list[str] = []

        for row in rows:
            if import_cost_is_set(row.cost_cny):
                already_cny += 1
                continue
            if row.is_warehouse_clearance:
                if import_cost_is_set(row.cost_vnd):
                    already_vnd += 1
                    continue
                warehouse_zero.append(row.id)
                if len(samples_wh) < 5:
                    samples_wh.append(f"{row.product_id} price={row.price} -> cost_vnd=0")
                continue
            if import_cost_is_set(row.cost_vnd):
                already_vnd += 1
                continue
            price = row.price
            try:
                price_f = float(price) if price is not None else 0.0
            except (TypeError, ValueError):
                price_f = 0.0
            if price_f <= 0:
                no_price += 1
                continue
            amount = listing_vnd_to_cny(price_f, rate)
            if amount is None or amount < 0:
                invert_failed += 1
                continue
            inverted.append((row.id, float(amount)))
            if len(samples_cny) < 5:
                samples_cny.append(f"{row.product_id} price={price_f:g} -> cost_cny={amount}")

        print(f"Ty gia loi nhuan (VND/CNY): {rate:g}")
        print(f"Tong san pham: {len(rows)}")
        print(f"Da co cost_cny: {already_cny}")
        print(f"Da co gia Viet Nam, bo qua: {already_vnd}")
        print(f"Thanh ly kho -> cost_vnd=0: {len(warehouse_zero)}")
        print(f"Dao gia ban -> cost_cny: {len(inverted)}")
        print(f"Khong co gia ban: {no_price}")
        print(f"Khong dao duoc: {invert_failed}")
        if samples_wh:
            print("Mau thanh ly:")
            for line in samples_wh:
                print(f"  {line}")
        if samples_cny:
            print("Mau dao gia te:")
            for line in samples_cny:
                print(f"  {line}")
        if not args.apply:
            print("Chua ghi. Chay lai voi --apply de cap nhat.")
            return

        cny_stmt = (
            update(Product)
            .where(Product.id == bindparam("b_id"))
            .values(cost_cny=bindparam("b_cny"))
        )
        vnd_stmt = (
            update(Product)
            .where(Product.id == bindparam("b_id"))
            .values(cost_vnd=bindparam("b_vnd"))
        )
        conn = db.connection()
        for start in range(0, len(warehouse_zero), _BATCH):
            chunk = warehouse_zero[start : start + _BATCH]
            conn.execute(vnd_stmt, [{"b_id": pid, "b_vnd": 0.0} for pid in chunk])
        for start in range(0, len(inverted), _BATCH):
            chunk = inverted[start : start + _BATCH]
            conn.execute(
                cny_stmt,
                [{"b_id": pid, "b_cny": amount} for pid, amount in chunk],
            )
        db.commit()
        print(f"Da ghi cost_vnd=0: {len(warehouse_zero)}")
        print(f"Da ghi cost_cny: {len(inverted)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
