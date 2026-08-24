"""Cache vector ảnh nhẹ + hit NanoAI image-search cho phối đồ PDP."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class ProductOutfitVisual(Base):
    __tablename__ = "product_outfit_visuals"

    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_url = Column(String(800))
    vector = Column(JSON, default=list)
    nano_hit_ids = Column(JSON, default=list)
    model_version = Column(String(32), default="v1", nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
