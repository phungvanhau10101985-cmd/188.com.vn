from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from datetime import datetime, timedelta

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    type = Column(String(50), default="general") # general, order, system, promotion
    is_read = Column(Boolean, default=False)
    
    # Thời điểm dự kiến gửi (hiển thị cho user từ lúc này)
    scheduled_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Thời điểm hết hạn (tự động xóa sau 15 ngày từ scheduled_at)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="notifications")
