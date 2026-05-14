"""Mã SKU nội bộ đã tải file (reserve TTL = INTERNAL_SKU_EXPORT_RESERVE_DAYS trong product_internal_sku).
Sau hết TTL bản ghi xóa — không còn chặn export trùng hay bắt buộc đối chiếu import."""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class InternalSkuExport(Base):
    __tablename__ = "internal_sku_exports"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(5), unique=True, nullable=False, index=True)
    exported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
