"""Kiểm tra filter shop same-shop: IN trên lower(trim()) tương đương OR từng shop."""

from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.product import Product


def _shop_key(value: str | None) -> str:
    return (value or "").strip().lower()


def test_shop_filter_in_matches_or():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    db.add_all(
        [
            Product(
                product_id="a1",
                name="Shop A",
                shop_name_chinese="  ShopAlpha  ",
                is_active=True,
            ),
            Product(
                product_id="b1",
                name="Shop B",
                shop_name_chinese="shopbeta",
                is_active=True,
            ),
            Product(
                product_id="c1",
                name="Inactive",
                shop_name_chinese="ShopAlpha",
                is_active=False,
            ),
            Product(
                product_id="d1",
                name="Other",
                shop_name_chinese="OtherShop",
                is_active=True,
            ),
        ]
    )
    db.commit()

    shops_lower = {"shopalpha", "shopbeta"}
    shop_cn_norm = func.lower(func.trim(Product.shop_name_chinese))

    via_in = (
        db.query(Product.id)
        .filter(
            shop_cn_norm.in_(list(shops_lower)),
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Product.id)
        .all()
    )
    via_or = (
        db.query(Product.id)
        .filter(
            or_(
                *[
                    func.lower(func.trim(Product.shop_name_chinese)) == shop_lower
                    for shop_lower in shops_lower
                ]
            ),
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Product.id)
        .all()
    )

    assert [r[0] for r in via_in] == [r[0] for r in via_or]
    db.close()
