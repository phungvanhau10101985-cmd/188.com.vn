"""Challenge lưu OTP + magic link (đăng nhập email), thay thế in-memory store."""
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func
from app.db.base import Base


class EmailLoginChallenge(Base):
    __tablename__ = "email_login_challenges"
    __table_args__ = (
        Index("ix_email_login_challenges_email_expires", "email_normalized", "expires_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    email_normalized = Column(String(255), nullable=False, index=True)
    otp_hash = Column(String(64), nullable=False)
    magic_token_hash = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
