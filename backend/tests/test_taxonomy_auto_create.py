"""Cascade bổ sung taxonomy: chỉ tạo cấp thiếu, tái dùng cấp có sẵn."""

import re

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.models.taxonomy_settings import TaxonomySettings
from app.models.product_review import ProductReview
from app.services.product_rating_question_groups import RATING_GROUP_ID_WHITELIST
from app.services.rating_group_alloc import list_rating_groups_without_reviews
from app.services.rating_group_seed_reviews import reviewer_name_gender


from app.services.taxonomy_auto_create import (
    ensure_additive_category_triple,
    is_taxonomy_auto_create_enabled,
    set_taxonomy_auto_create_enabled,
    validate_proposed_category_names,
)

_RESERVED = set(RATING_GROUP_ID_WHITELIST) | {0, 88, 99, 100, 888, 1000}


def _reply_has(text: str, word: str) -> bool:
    return re.search(rf"(^|\s){word}([\s,.]|$)", (text or "").casefold()) is not None


def _assert_fresh_group(gid):
    assert isinstance(gid, int) and gid >= 101
    assert gid not in _RESERVED


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
    assert c1.rating_group_id is None
    assert c2.rating_group_id is None
    _assert_fresh_group(c3.rating_group_id)
    assert out["rating_group_id"] == str(c3.rating_group_id)


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
    c3_new = db.query(Category).filter(Category.level == 3).one()
    assert c2_new.rating_group_id is None
    _assert_fresh_group(c3_new.rating_group_id)
    assert c1.rating_group_id is None


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
    _assert_fresh_group(c3.rating_group_id)
    parents = db.query(Category).filter(Category.level.in_((1, 2))).all()
    assert len(parents) == 2
    assert all(c.rating_group_id is None for c in parents)


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


def test_auto_create_flag_follows_settings_row():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[TaxonomySettings.__table__])
    db = sessionmaker(bind=engine)()
    assert is_taxonomy_auto_create_enabled(db) is bool(
        getattr(settings, "IMPORT_LINK_TAXONOMY_AUTO_CREATE_ENABLED", True)
    )
    set_taxonomy_auto_create_enabled(db, False)
    db.commit()
    assert is_taxonomy_auto_create_enabled(db) is False
    set_taxonomy_auto_create_enabled(db, True)
    db.commit()
    assert is_taxonomy_auto_create_enabled(db) is True


def test_new_cat3_seeds_100_matching_reviews_and_leaves_pending_list():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Category.__table__, SeoCluster.__table__, ProductReview.__table__]
    )
    db = sessionmaker(bind=engine)()
    out, warnings = ensure_additive_category_triple(db, "Thú cưng XYZ", "Phụ kiện chó", "Vòng cổ chó da")
    db.commit()
    assert out is not None
    gid = int(out["rating_group_id"])
    rows = db.query(ProductReview).filter(ProductReview.group == gid).all()
    assert len(rows) == 100
    assert all(r.is_imported and r.product_id is None for r in rows)
    assert all(r.star in (4, 5) for r in rows)
    assert any(r.star == 4 for r in rows)
    assert len({r.content for r in rows}) == 100
    assert all("vòng cổ" in (r.content or "").casefold() for r in rows)
    assert all("vòng cổ chó da" not in (r.content or "").casefold() for r in rows)
    genders = {reviewer_name_gender(r.user_name) for r in rows}
    assert genders == {"female", "male"}
    assert sum(reviewer_name_gender(r.user_name) == "female" for r in rows) == 50
    for r in rows:
        g = reviewer_name_gender(r.user_name)
        if g == "female":
            assert _reply_has(r.reply_content or "", "chị")
            assert not _reply_has(r.reply_content or "", "anh")
        else:
            assert _reply_has(r.reply_content or "", "anh")
            assert not _reply_has(r.reply_content or "", "chị")
    blob = " ".join((r.content or "").casefold() for r in rows)
    assert "váy" not in blob and "giày" not in blob
    assert all(r.reply_name == "188.COM.VN" and (r.reply_content or "").strip() for r in rows)
    assert any("đã tạo 100 đánh giá" in w for w in warnings)
    assert list_rating_groups_without_reviews(db) == []

    again, _w2 = ensure_additive_category_triple(db, "Thú cưng XYZ", "Phụ kiện chó", "Vòng cổ chó da")
    db.commit()
    assert again is not None
    assert db.query(ProductReview).filter(ProductReview.group == gid).count() == 100

    out2, _w3 = ensure_additive_category_triple(db, "Thú cưng XYZ", "Phụ kiện chó", "Dây dắt chó")
    db.commit()
    assert out2 is not None
    gid2 = int(out2["rating_group_id"])
    assert gid2 != gid
    rows2 = db.query(ProductReview).filter(ProductReview.group == gid2).all()
    assert len(rows2) == 100
    assert all("dây dắt" in (r.content or "").casefold() for r in rows2)
    assert all("dây dắt chó" not in (r.content or "").casefold() for r in rows2)


def test_reviewer_names_follow_product_gender():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[Category.__table__, SeoCluster.__table__, ProductReview.__table__]
    )
    db = sessionmaker(bind=engine)()

    female, _w = ensure_additive_category_triple(db, "Giày dép Nữ", "Sandal nữ", "Dép quai ngang nữ")
    male, _w2 = ensure_additive_category_triple(db, "Giày dép Nam", "Sneaker nam", "Giày chạy bộ nam")
    db.commit()

    def names_for(out):
        gid = int(out["rating_group_id"])
        return db.query(ProductReview).filter(ProductReview.group == gid).all()

    women = names_for(female)
    men = names_for(male)
    assert len(women) == 100 and len(men) == 100
    assert {reviewer_name_gender(r.user_name) for r in women} == {"female"}
    assert {reviewer_name_gender(r.user_name) for r in men} == {"male"}
    assert all(_reply_has(r.reply_content or "", "chị") for r in women)
    assert all(not _reply_has(r.reply_content or "", "anh") for r in women)
    assert all(_reply_has(r.reply_content or "", "anh") for r in men)
    assert all(not _reply_has(r.reply_content or "", "chị") for r in men)
    assert all("dép" in (r.content or "").casefold() for r in women)
    assert all("quai ngang" not in (r.content or "").casefold() for r in women)
    assert all("giày" in (r.content or "").casefold() for r in men)
    assert all("chạy bộ" not in (r.content or "").casefold() for r in men)
