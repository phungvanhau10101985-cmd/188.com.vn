"""OTP step-up challenges and administrator trusted devices."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class AuthActionChallenge(Base):
    __tablename__ = "auth_action_challenges"
    __table_args__ = (
        Index("ix_auth_action_challenges_subject_purpose", "subject_type", "subject_id", "purpose"),
    )

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String(64), nullable=False, unique=True, index=True)
    subject_type = Column(String(16), nullable=False, index=True)
    subject_id = Column(Integer, nullable=False, index=True)
    purpose = Column(String(64), nullable=False, index=True)
    otp_hash = Column(String(64), nullable=False)
    payload_hash = Column(String(64), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminTrustedDevice(Base):
    __tablename__ = "admin_trusted_devices"
    __table_args__ = (
        Index("ix_admin_trusted_devices_admin_token", "admin_id", "token_hash"),
    )

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now())
