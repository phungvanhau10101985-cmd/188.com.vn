"""Singleton id=1: admin bật/tắt tạo danh mục mới khi cào hoặc import thiếu nhánh."""

from sqlalchemy import Boolean, Column, DateTime, Integer
from sqlalchemy.sql import func

from app.db.base import Base


class TaxonomySettings(Base):
    __tablename__ = "taxonomy_settings"

    id = Column(Integer, primary_key=True)
    auto_create_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<TaxonomySettings(auto_create={self.auto_create_enabled})>"
