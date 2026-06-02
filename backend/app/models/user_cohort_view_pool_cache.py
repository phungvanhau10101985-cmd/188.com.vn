"""Cache pool tối đa 100 SP xem gần nhất của nhóm cùng tuổi/giới — tránh query peer mỗi lần mở trang chủ."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from app.db.base import Base


class UserCohortViewPoolCache(Base):
    __tablename__ = "user_cohort_view_pool_cache"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    version_key = Column(String(200), nullable=False, index=True)
    cohort_mode = Column(String(32), nullable=False)
    product_ids = Column(JSON, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
