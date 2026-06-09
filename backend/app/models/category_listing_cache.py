"""Cache JSON lưới sản phẩm danh mục storefront."""

from sqlalchemy import Boolean, Column, DateTime, String, Text, func

from app.db.base import Base


class CategoryListingCache(Base):
    __tablename__ = "category_listing_cache"

    cache_key = Column(String(64), primary_key=True, index=True)
    response_json = Column(Text, nullable=False)
    cache_query_json = Column(Text, nullable=False)
    category_path = Column(String(1000), nullable=False, index=True)
    sort = Column(String(32), nullable=False, default="random", index=True)
    is_stale = Column(Boolean, default=False, nullable=False, index=True)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
