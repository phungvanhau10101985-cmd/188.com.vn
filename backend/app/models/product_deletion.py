"""Tombstone cho API đồng bộ catalog gia tăng với hệ thống đối tác."""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class ProductDeletion(Base):
    """
    Lưu dấu xóa trước khi Product bị hard-delete.

    `product_id` là khóa public gửi cho đối tác; mỗi mã chỉ giữ tombstone mới nhất.
    """

    __tablename__ = "product_deletions"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_deletions_product_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(String(255), nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
