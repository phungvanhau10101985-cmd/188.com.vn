"""Snapshot gợi ý trang chủ (phiên khách) — đọc nhanh sau khi away rebuild."""

from sqlalchemy import Column, DateTime, String, JSON, func

from app.db.base import Base


class GuestHomeRecommendationSnapshot(Base):
    __tablename__ = "guest_home_recommendation_snapshots"

    guest_session_id = Column(String(64), primary_key=True)
    version_key = Column(String(200), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
