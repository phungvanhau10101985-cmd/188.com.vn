"""Import Excel gán nhóm đánh giá của cat3 và sinh đánh giá dựng sẵn."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.category import Category
from app.models.product_review import ProductReview
from app.models.seo_cluster import SeoCluster
from app.services.import_category_rating import apply_import_category_rating_group


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Category.__table__, SeoCluster.__table__, ProductReview.__table__],
    )
    return sessionmaker(bind=engine)()


def _row(**overrides):
    data = {
        "category": "Giày dép Nữ",
        "subcategory": "Boot Nữ",
        "sub_subcategory": "Boot Martin cổ ngắn Nữ",
        "group_rating": 102,
    }
    data.update(overrides)
    return data


def test_missing_cat3_keeps_file_group_and_seeds_reviews():
    db = _db()
    row = _row()
    warnings = apply_import_category_rating_group(db, row)
    db.commit()

    assert row["group_rating"] == 102
    cat3 = db.query(Category).filter(Category.level == 3).one()
    assert cat3.rating_group_id == 102
    assert row["category_id"] == cat3.id
    assert cat3.name == "Boot Martin cổ ngắn Nữ"
    reviews = db.query(ProductReview).filter(ProductReview.group == 102).all()
    assert len(reviews) == 100
    assert all(r.product_id is None and r.is_imported for r in reviews)
    assert any("nhận nhóm đánh giá 102" in w or "nhóm đánh giá 102" in w for w in warnings)
    assert any("đã tạo 100 đánh giá" in w for w in warnings)

    again = _row()
    apply_import_category_rating_group(db, again)
    db.commit()
    assert again["group_rating"] == 102
    assert db.query(ProductReview).filter(ProductReview.group == 102).count() == 100
    assert db.query(Category).filter(Category.level == 3).count() == 1


def test_existing_cat3_without_group_receives_file_group():
    db = _db()
    c1 = Category(
        external_id="c1",
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
        external_id="c2",
        parent_id=c1.id,
        level=2,
        name="Boot Nữ",
        slug="boot-nu",
        full_slug="giay-dep-nu/boot-nu",
        is_active=True,
        seo_index=True,
    )
    db.add(c2)
    db.flush()
    c3 = Category(
        external_id="c3",
        parent_id=c2.id,
        level=3,
        name="Boot Martin cổ ngắn Nữ",
        slug="boot-martin-co-ngan-nu",
        full_slug="giay-dep-nu/boot-nu/boot-martin-co-ngan-nu",
        is_active=True,
        seo_index=False,
    )
    db.add(c3)
    db.commit()

    row = _row()
    warnings = apply_import_category_rating_group(db, row)
    db.commit()

    db.refresh(c3)
    assert c3.rating_group_id == 102
    assert row["group_rating"] == 102
    assert row["category_id"] == c3.id
    assert db.query(ProductReview).filter(ProductReview.group == 102).count() == 100
    assert any("nhận nhóm đánh giá 102" in w for w in warnings)
    assert db.query(Category).filter(Category.level == 3).count() == 1


def test_product_takes_group_already_on_cat3_and_seeds_if_empty():
    db = _db()
    c1 = Category(
        external_id="c1",
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
        external_id="c2",
        parent_id=c1.id,
        level=2,
        name="Boot Nữ",
        slug="boot-nu",
        full_slug="giay-dep-nu/boot-nu",
        is_active=True,
        seo_index=True,
    )
    db.add(c2)
    db.flush()
    c3 = Category(
        external_id="c3",
        parent_id=c2.id,
        level=3,
        name="Boot Martin cổ ngắn Nữ",
        slug="boot-martin",
        full_slug="giay-dep-nu/boot-nu/boot-martin",
        is_active=True,
        seo_index=False,
        rating_group_id=205,
    )
    db.add(c3)
    db.commit()

    row = _row(group_rating=14)
    apply_import_category_rating_group(db, row)
    db.commit()

    assert row["group_rating"] == 205
    assert row["category_id"] == c3.id
    assert db.query(ProductReview).filter(ProductReview.group == 205).count() == 100
    assert db.query(ProductReview).filter(ProductReview.group == 14).count() == 0


def test_shared_legacy_group_does_not_create_category_or_reviews():
    db = _db()
    row = _row(group_rating=24)
    warnings = apply_import_category_rating_group(db, row)
    db.commit()

    assert row["group_rating"] == 24
    assert row.get("category_id") in (None, 0)
    assert db.query(Category).count() == 0
    assert db.query(ProductReview).count() == 0
    assert warnings == []


def test_second_row_reuses_cache_without_extra_reviews():
    db = _db()
    cache = {}
    first = _row()
    apply_import_category_rating_group(db, first, cache=cache)
    db.commit()
    second = _row(group_rating=14)
    warnings = apply_import_category_rating_group(db, second, read_cache=cache)
    assert second["group_rating"] == 102
    assert second["category_id"] == first["category_id"]
    assert warnings == []
    assert db.query(ProductReview).filter(ProductReview.group == 102).count() == 100
