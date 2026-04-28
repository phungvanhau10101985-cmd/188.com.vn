# Thiết bị đã xác thực OTP: đăng nhập lại chỉ cần email + cùng mã thiết bị (localStorage) trên trình duyệt đó.
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class UserTrustedDevice(Base):
    __tablename__ = "user_trusted_devices"
    __table_args__ = (UniqueConstraint("user_id", "device_token_hash", name="uq_user_device_token"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_token_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
