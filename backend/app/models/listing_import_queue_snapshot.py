"""Snapshot JSON hàng đợi import listing (admin) — thay file disk; worker đọc/ghi qua DB."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.db.base import Base


class ListingImportQueueSnapshot(Base):
    """Trạng thái đầy đủ một đợt (queue_token + items + flags pause/stop)."""

    __tablename__ = "listing_import_queue_snapshots"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    queue_token = Column(String(64), unique=True, nullable=False, index=True)
    payload_json = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ListingImportQueueRevocation(Base):
    """
    Token đã xóa chủ động: chặn worker ghi lại snapshot sau khi DELETE,
    và load_queue không đọc file legacy (tránh tái tạo hàng đợi).
    """

    __tablename__ = "listing_import_queue_revocations"

    queue_token = Column(String(64), primary_key=True)
    revoked_at = Column(DateTime(timezone=True), server_default=func.now())
