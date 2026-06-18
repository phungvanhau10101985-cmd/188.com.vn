"""Cấu hình lịch backup VPS & nhật ký các lần chạy."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


class VpsBackupSettings(Base):
    __tablename__ = "vps_backup_settings"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=False, nullable=False)
    hour = Column(Integer, default=3, nullable=False)
    minute = Column(Integer, default=0, nullable=False)
    # Python weekday: 0=Thứ Hai … 6=Chủ Nhật
    days_of_week = Column(JSON, default=lambda: [0, 1, 2, 3, 4, 5, 6], nullable=False)
    keep_count = Column(Integer, default=2, nullable=False)
    retention_days = Column(Integer, default=2, nullable=False)  # legacy — dùng keep_count
    include_cache = Column(Boolean, default=False, nullable=False)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VpsBackupRun(Base):
    __tablename__ = "vps_backup_runs"

    id = Column(Integer, primary_key=True, index=True)
    trigger = Column(String(20), nullable=False, default="manual")
    status = Column(String(20), nullable=False, default="queued", index=True)
    archive_filename = Column(String(255), nullable=True)
    archive_path = Column(String(512), nullable=True)
    archive_size_bytes = Column(BigInteger, nullable=True)
    keep_count = Column(Integer, nullable=True)
    retention_days = Column(Integer, nullable=True)
    include_cache = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)
    log_tail = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
