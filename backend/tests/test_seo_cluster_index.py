"""SEO cluster index + cat3 redirect sang /c/<slug>."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.category import Category
from app.models.seo_cluster import SeoCluster
from app.services.category_seo_analyzer import get_category_seo_status
from app.services.seo_cluster_index import cluster_is_indexable


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Category.__table__, SeoCluster.__table__])
    return sessionmaker(bind=engine)()


def test_cluster_is_indexable_empty_is_false():
    assert cluster_is_indexable("index", 0) is False
    assert cluster_is_indexable("index", 1) is True
    assert cluster_is_indexable("noindex", 100) is False


def test_cat3_path_redirects_to_cluster():
    db = _db()
    c1 = Category(
        external_id="cat1__tui-xach-nam",
        parent_id=None,
        level=1,
        name="Túi xách Nam",
        slug="tui-xach-nam",
        full_slug="tui-xach-nam",
        is_active=True,
        seo_index=True,
    )
    db.add(c1)
    db.flush()
    c2 = Category(
        external_id="cat2__tui-xach-nam__ba-lo-nam",
        parent_id=c1.id,
        level=2,
        name="Ba lô Nam",
        slug="ba-lo-nam",
        full_slug="tui-xach-nam/ba-lo-nam",
        is_active=True,
        seo_index=True,
    )
    db.add(c2)
    db.flush()
    cluster = SeoCluster(
        external_id="cluster__ba-lo-laptop-nam-15-inch",
        slug="ba-lo-laptop-nam-15-inch",
        name="ba lô laptop nam 15 inch",
        canonical_path="/c/ba-lo-laptop-nam-15-inch",
        index_policy="index",
    )
    db.add(cluster)
    db.flush()
    c3 = Category(
        external_id="cat3__tui-xach-nam__ba-lo-nam__ba-lo-laptop-nam-15-inch",
        parent_id=c2.id,
        level=3,
        name="ba lô laptop nam 15 inch",
        slug="ba-lo-laptop-nam-15-inch",
        full_slug="tui-xach-nam/ba-lo-nam/ba-lo-laptop-nam-15-inch",
        is_active=True,
        seo_index=False,
        seo_cluster_id=cluster.id,
    )
    db.add(c3)
    db.commit()

    status = get_category_seo_status(db, "tui-xach-nam/ba-lo-nam/ba-lo-laptop-nam-15-inch")
    assert status["should_redirect"] is True
    assert status["redirect_to"] == "/c/ba-lo-laptop-nam-15-inch"
    assert status["seo_indexable"] is False

    l2 = get_category_seo_status(db, "tui-xach-nam/ba-lo-nam")
    assert l2["should_redirect"] is False
    assert l2["seo_indexable"] is True
