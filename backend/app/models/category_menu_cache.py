"""Cache JSON cây menu danh mục (GET /categories/from-products) — dùng chung mọi khách."""

from sqlalchemy import Boolean, Column, DateTime, String, Text, func

from app.db.base import Base


class CategoryMenuCache(Base):
    __tablename__ = "category_menu_cache"

    cache_key = Column(String(64), primary_key=True, index=True)
    tree_json = Column(Text, nullable=False)
    is_stale = Column(Boolean, default=False, nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
