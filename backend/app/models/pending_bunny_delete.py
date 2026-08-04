"""Hàng đợi xoá object Bunny CDN sau khi xóa sản phẩm DB — bền vững qua restart."""

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class PendingBunnyDelete(Base):
    """
    Mỗi dòng = một storage path cần DELETE trên Bunny.
    Cron / thread nền xử lý; xóa dòng khi thành công.
    """

    __tablename__ = "pending_bunny_deletes"
    __table_args__ = (UniqueConstraint("storage_path", name="uq_pending_bunny_deletes_storage_path"),)

    id = Column(Integer, primary_key=True, index=True)
    storage_path = Column(String(1024), nullable=False, index=True)
    source_url = Column(Text, nullable=True)
    product_id = Column(String(255), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending | failed
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
