from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db.base import Base


class ProductImportDraft(Base):
    __tablename__ = "product_import_drafts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), unique=True, index=True, nullable=False)
    source = Column(String(50), default="1688", index=True)
    source_url = Column(Text, nullable=False)
    source_offer_id = Column(String(100), index=True)
    status = Column(String(30), default="queued", index=True)
    phase = Column(String(50), default="queued")
    message = Column(Text)
    percent = Column(Integer, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    product_data = Column(JSON, nullable=True)
    excel_overlays = Column(JSON, nullable=True)  # Giá/trường từ file Excel bulk (shop_name, price, ...)
    errors = Column(JSON, default=list)
    warnings = Column(JSON, default=list)
    created_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    published_product_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
