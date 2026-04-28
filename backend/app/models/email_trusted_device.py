"""Thiết bị tin cậy sau OTP (checkbox ~30 ngày), tra cứu theo email + browser_id."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class EmailTrustedDevice(Base):
    __tablename__ = "email_trusted_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "browser_id_hash", name="uq_email_trusted_user_browser"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    email_normalized = Column(String(255), nullable=False, index=True)
    browser_id_hash = Column(String(64), nullable=False, index=True)
    token_hash = Column(String(64), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
