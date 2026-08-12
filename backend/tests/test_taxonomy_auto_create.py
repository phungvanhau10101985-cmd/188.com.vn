"""Cascade bổ sung taxonomy: chỉ tạo cấp thiếu, tái dùng cấp có sẵn."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.services.taxonomy_auto_create import (
    ensure_additive_category_triple,
    validate_proposed_category_names,
)


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Category.__table__, SeoCluster.__table__])
    return sessionmaker(bind=engine)()


def _seed_cat1_cat2(db):
    c1 = Category(
        external_id="cat1__giay-dep-nu",
        parent_id=None,
        level=1,
        name="Giày dép Nữ",
        slug="giay-dep-nu",
        full_slug="giay-dep-nu",
        is_active=True,
        seo_index=True,
    )
    db.add(c1)
    db.flush()
    c2 = Category(
        external_id="cat2__giay-dep-nu__dep-sandal-nu",
        parent_id=c1.id,
        level=2,
        name="Dép sandal nữ",
        slug="dep-sandal-nu",
        full_slug="giay-dep-nu/dep-sandal-nu",
        is_active=True,
        seo_index=True,
    )
    db.add(c2)
    db.commit()
    return c1, c2


def test_validate_rejects_cjk():
    assert validate_proposed_category_names("Giày", "Sandal", "拖鞋") is not None
    assert validate_proposed_category_names("Giày dép Nữ", "Sandal", "Dép quai ngang") is None


def test_create_only_cat3_when_cat1_cat2_exist():
    db = _db()
    c1, c2 = _seed_cat1_cat2(db)
    before = db.query(Category).count()

    out, warnings = ensure_additive_category_triple(
        db, "Giày dép Nữ", "Dép sandal nữ", "Dép quai ngang nữ mới"
    )
    db.commit()

    assert out is not None
    assert out["cat1"] == "Giày dép Nữ"
    assert out["cat2"] == "Dép sandal nữ"
    assert out["cat3"] == "Dép quai ngang nữ mới"
    assert out["created_levels"] == "3"
    assert db.query(Category).count() == before + 1
    c3 = db.query(Category).filter(Category.level == 3).one()
    assert c3.parent_id == c2.id
    assert (c3.external_id or "").startswith("auto__")
    assert any("đã tạo cat3" in w for w in warnings)


def test_create_cat2_and_cat3_when_only_cat1_exists():
    db = _db()
    c1, _c2 = _seed_cat1_cat2(db)
    before = db.query(Category).count()

    out, _w = ensure_additive_category_triple(
        db, "Giày dép Nữ", "Boot nữ mới", "Boot cổ ngắn nữ"
    )
    db.commit()

    assert out is not None
    assert out["created_levels"] == "2,3"
    assert db.query(Category).count() == before + 2
    c2_new = (
        db.query(Category)
        .filter(Category.level == 2, Category.name == "Boot nữ mới")
        .one()
    )
    assert c2_new.parent_id == c1.id


def test_create_full_triple_when_cat1_missing():
    db = _db()
    before = db.query(Category).count()

    out, warnings = ensure_additive_category_triple(
        db, "Thú cưng XYZ", "Phụ kiện chó", "Vòng cổ chó da"
    )
    db.commit()

    assert out is not None
    assert out["created_levels"] == "1,2,3"
    assert db.query(Category).count() == before + 3
    assert db.query(Category).filter(Category.level == 1).count() == 1
    assert any("đã tạo cat1" in w for w in warnings)
    c3 = db.query(Category).filter(Category.level == 3).one()
    assert c3.seo_cluster_id is not None


def test_reuse_existing_full_triple_no_create():
    db = _db()
    _c1, c2 = _seed_cat1_cat2(db)
    c3 = Category(
        external_id="cat3__x",
        parent_id=c2.id,
        level=3,
        name="Dép tông nữ",
        slug="dep-tong-nu",
        full_slug="giay-dep-nu/dep-sandal-nu/dep-tong-nu",
        is_active=True,
        seo_index=False,
    )
    db.add(c3)
    db.commit()
    before = db.query(Category).count()

    out, warnings = ensure_additive_category_triple(
        db, "Giày dép Nữ", "Dép sandal nữ", "Dép tông nữ"
    )
    assert out is not None
    assert out["created_levels"] == ""
    assert db.query(Category).count() == before
    assert any("dùng nhánh có sẵn" in w for w in warnings)


def test_does_not_rename_existing_cat1():
    db = _db()
    _seed_cat1_cat2(db)
    out, _w = ensure_additive_category_triple(
        db, "giay dep nu", "Dép sandal nữ", "Leaf mới"
    )
    db.commit()
    assert out is not None
    # khớp theo slug → giữ tên chuẩn DB
    assert out["cat1"] == "Giày dép Nữ"
    assert db.query(Category).filter(Category.level == 1).count() == 1
