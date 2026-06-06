"""Kiểm tra SP hết hàng mọi phiên bản: tồn nguồn = 0 và không còn dòng kho thanh lý."""
from collections import defaultdict

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.product import Product
from app.services.warehouse_clearance import (
    _resolve_base_sku_for_parent,
    find_parent_product_by_base_sku,
    is_source_product_oos,
)
from app.services.warehouse_stock import warehouse_sellable_qty


def source_sellable(p: Product) -> int:
    if is_source_product_oos(p):
        return 0
    return max(0, int(p.available or 0))


def main() -> None:
    db = SessionLocal()
    try:
        wh_sellable_by_base: dict[str, int] = defaultdict(int)
        wh_rows = db.query(Product).filter(Product.is_warehouse_clearance == True).all()  # noqa: E712
        for wh in wh_rows:
            base = (wh.base_sku or "").strip()
            if not base and wh.product_id and "/" in str(wh.product_id):
                base = str(wh.product_id).split("/")[0].strip()
            if not base:
                base = (wh.code or "").strip()
            if base:
                wh_sellable_by_base[base] += warehouse_sellable_qty(wh)

        parents = (
            db.query(Product)
            .filter(or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None)))
            .all()
        )

        fully_oos_active: list[dict] = []
        fully_oos_inactive: list[dict] = []
        partial: list[tuple] = []

        for p in parents:
            base = _resolve_base_sku_for_parent(p) or ""
            src = source_sellable(p)
            wh = wh_sellable_by_base.get(base, 0) if base else 0
            if src <= 0 and wh <= 0:
                row = {
                    "id": p.id,
                    "product_id": p.product_id,
                    "code": p.code,
                    "name": (p.name or "")[:80],
                    "available": p.available,
                    "source_stock_status": p.source_stock_status,
                    "is_active": p.is_active,
                    "base_sku": base,
                }
                if p.is_active:
                    fully_oos_active.append(row)
                else:
                    fully_oos_inactive.append(row)
            elif src <= 0 and wh > 0:
                partial.append((p.id, p.product_id, wh))

        standalone_active_oos = []
        standalone_oos = 0
        for wh in wh_rows:
            parsed_base = (wh.base_sku or "").strip()
            if not parsed_base and wh.product_id:
                parsed_base = (
                    str(wh.product_id).split("/")[0]
                    if "/" in str(wh.product_id)
                    else str(wh.product_id)
                )
            parent = find_parent_product_by_base_sku(db, parsed_base) if parsed_base else None
            if parent is not None:
                continue
            if warehouse_sellable_qty(wh) <= 0:
                standalone_oos += 1
                if wh.is_active:
                    standalone_active_oos.append(wh)

        print("=== TONG QUAN ===")
        print(f"SP goc (khong phai dong kho): {len(parents)}")
        print(f"Dong kho thanh ly: {len(wh_rows)}")
        print()
        print("SP goc HET HANG MOI PHIEN BAN (ton nguon=0 va kho TL=0):")
        print(f"  - dang hien thi (is_active): {len(fully_oos_active)}")
        print(f"  - an / khong hien thi: {len(fully_oos_inactive)}")
        print(f"  - tong: {len(fully_oos_active) + len(fully_oos_inactive)}")
        print()
        print(f"SP goc: nguon het nhung con kho thanh ly: {len(partial)}")
        print()
        print("Dong kho doc lap (khong SP goc) het hang:")
        print(f"  - dang active: {len(standalone_active_oos)}")
        print(f"  - tong: {standalone_oos}")
        print()
        print("=== MAU 20 SP GOC DANG HIEN THI - HET HANG MOI PHIEN BAN ===")
        for r in fully_oos_active[:20]:
            print(
                f"  id={r['id']} pid={r['product_id']} avail={r['available']} "
                f"src={r['source_stock_status']!r} base={r['base_sku']}"
            )
            print(f"    {r['name']}")
        if len(fully_oos_active) > 20:
            print(f"  ... va {len(fully_oos_active) - 20} SP khac")
    finally:
        db.close()


if __name__ == "__main__":
    main()
