"""
Cache pool sản phẩm cohort cho khách chưa đăng nhập — theo NHÓM nhân khẩu học tự khai
(`bucket_key`, ví dụ "female:1998" hoặc "female:_any"), KHÔNG theo từng guest riêng lẻ.
Nhiều guest cùng bucket dùng chung 1 pool đã cache — hiệu quả hơn cache per-user.
"""

from sqlalchemy import Column, DateTime, Integer, JSON, String, func

from app.db.base import Base


class GuestCohortPoolCache(Base):
    __tablename__ = "guest_cohort_view_pool_cache"

    bucket_key = Column(String(64), primary_key=True)
    cohort_mode = Column(String(32), nullable=False)
    product_ids = Column(JSON, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
