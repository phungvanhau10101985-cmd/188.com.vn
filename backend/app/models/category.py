# backend/app/models/category.py - PRODUCTION READY (taxonomy v2)
"""
Category: cây danh mục 3 cấp.
- `parent_id`: self-FK; cấp 1 thì NULL.
- `full_slug`: UNIQUE, dùng làm khoá lookup khi import sản phẩm (vd `giay-dep-nam/sneaker-giay-chay-nam/giay-chay-trail-nam`).
- `seo_index`: True cho cat1/cat2, False cho cat3 (cat3 noindex, gom về `seo_cluster`).
- `seo_cluster_id`: chỉ cat3 mới trỏ. Cat1/cat2 = NULL.
- `external_id`: id chuỗi từ taxonomy_import.xlsx (vd `cat3__giay-dep-nam__...`) để upsert ổn định khi re-import.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)

    external_id = Column(String(200), unique=True, index=True)
    parent_id = Column(
        Integer,
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    level = Column(Integer, default=1, nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(300), index=True, nullable=False)
    full_slug = Column(String(800), unique=True, index=True, nullable=False)
    description = Column(Text)
    image = Column(String(500))
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    seo_index = Column(Boolean, default=True, nullable=False)
    seo_cluster_id = Column(
        Integer,
        ForeignKey("seo_clusters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Self-relationship cha-con
    parent = relationship(
        "Category",
        remote_side="Category.id",
        back_populates="children",
        foreign_keys=[parent_id],
    )
    children = relationship(
        "Category",
        back_populates="parent",
        foreign_keys=[parent_id],
        cascade="all, delete-orphan",
        single_parent=True,
    )

    # Cluster (chỉ cat3 dùng)
    seo_cluster = relationship(
        "SeoCluster",
        back_populates="categories",
        foreign_keys=[seo_cluster_id],
    )

    # Một Category (cat3) có nhiều Product
    products = relationship(
        "Product",
        back_populates="category_rel",
        lazy="dynamic",
        cascade="all, delete-orphan",
        foreign_keys="[Product.category_id]",
    )

    def __repr__(self):
        return f"<Category L{self.level} {self.full_slug}>"
