"""Bộ phối PDP đã tính sẵn — lần sau chỉ đọc id sản phẩm."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class ProductOutfitPick(Base):
    __tablename__ = "product_outfit_picks"

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    algo_version = Column(String(32), nullable=False, default="v8")
    payload = Column(JSON, nullable=False, default=dict)
    visual_ready = Column(Boolean, default=False, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
