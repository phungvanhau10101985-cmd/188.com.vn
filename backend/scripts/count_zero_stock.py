"""Đếm SP có tồn kho (available) = 0 hoặc NULL."""
from sqlalchemy import func, or_

from app.db.session import SessionLocal
from app.models.product import Product


def main() -> None:
    db = SessionLocal()
    try:
        zero = func.coalesce(Product.available, 0) <= 0
        total = db.query(Product).count()
        z_all = db.query(Product).filter(zero).count()
        z_active = db.query(Product).filter(zero, Product.is_active == True).count()
        z_parent = (
            db.query(Product)
            .filter(zero, or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None)))
            .count()
        )
        z_parent_active = (
            db.query(Product)
            .filter(
                zero,
                or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None)),
                Product.is_active == True,
            )
            .count()
        )
        z_wh = db.query(Product).filter(zero, Product.is_warehouse_clearance == True).count()
        z_wh_active = (
            db.query(Product).filter(zero, Product.is_warehouse_clearance == True, Product.is_active == True).count()
        )

        print(f"Tong SP trong DB: {total}")
        print("SP co ton kho (available) = 0 hoac NULL:")
        print(f"  - tat ca: {z_all}")
        print(f"  - dang hien thi (is_active): {z_active}")
        print(f"  - SP goc (khong dong kho): {z_parent} | active: {z_parent_active}")
        print(f"  - dong kho thanh ly: {z_wh} | active: {z_wh_active}")
        print()
        print("Mau 10 SP goc active, available=0:")
        rows = (
            db.query(Product)
            .filter(or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None)))
            .filter(Product.is_active == True, zero)
            .order_by(Product.id.desc())
            .limit(10)
            .all()
        )
        for p in rows:
            name = (p.name or "")[:50]
            print(f"  id={p.id} pid={p.product_id} avail={p.available} src={p.source_stock_status!r} | {name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
