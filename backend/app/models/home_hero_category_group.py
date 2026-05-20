"""Nhóm tile danh mục hero trang chủ — tính sẵn (2 Nam + 2 Nữ) từ lượt xem SP."""
from sqlalchemy import Column, DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class HomeHeroCategoryGroup(Base):
    __tablename__ = "home_hero_category_groups"
    __table_args__ = (
        UniqueConstraint("gender", "group_index", name="uq_home_hero_cat_gender_group"),
    )

    id = Column(Integer, primary_key=True, index=True)
    gender = Column(String(8), nullable=False, index=True)  # Nam | Nữ
    group_index = Column(Integer, nullable=False)  # 1 hoặc 2
    tiles = Column(JSON, nullable=False, default=list)
    heading = Column(String(128), nullable=True)
    subtitle = Column(String(256), nullable=True)
    anchor_category = Column(String(255), nullable=True)
    view_score_total = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
