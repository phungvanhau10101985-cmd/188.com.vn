"""Cache bộ lọc listing (size/màu/kiểu/giá) theo danh mục, từ khóa tìm kiếm, SEO cluster."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, UniqueConstraint, func

from app.db.base import Base


class ListingFacetCache(Base):
    __tablename__ = "listing_facet_cache"
    __table_args__ = (UniqueConstraint("scope_type", "scope_key", name="uq_listing_facet_scope"),)

    id = Column(Integer, primary_key=True, index=True)
    scope_type = Column(String(32), nullable=False, index=True)
    scope_key = Column(String(500), nullable=False, index=True)
    display_label = Column(String(500), nullable=True)

    sizes_json = Column(JSON, nullable=False, default=list)
    colors_json = Column(JSON, nullable=False, default=list)
    style_tags_json = Column(JSON, nullable=False, default=list)
    price_min = Column(Float, nullable=True)
    price_max = Column(Float, nullable=True)
    product_count = Column(Integer, default=0, nullable=False)

    is_manual = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    is_stale = Column(Boolean, default=False, nullable=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
