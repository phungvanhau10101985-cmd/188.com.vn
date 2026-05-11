"""Các mã SKU nội bộ ([A-Z][0-9]{4}, thực tế A0001–Z9999, không phát hành X0000) đã xuất file nhưng có thể chưa gán vào sản phẩm."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class InternalSkuExport(Base):
    __tablename__ = "internal_sku_exports"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(5), unique=True, nullable=False, index=True)
    exported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
