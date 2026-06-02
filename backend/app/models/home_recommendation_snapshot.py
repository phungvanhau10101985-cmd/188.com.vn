"""Snapshot gợi ý trang chủ (đăng nhập) — hiển thị tức thì phiên trước, rebuild mỗi lần mở trang."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from app.db.base import Base


class UserHomeRecommendationSnapshot(Base):
    __tablename__ = "user_home_recommendation_snapshots"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    version_key = Column(String(200), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
