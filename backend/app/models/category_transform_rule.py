from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func
from app.db.base import Base


class CategoryTransformRule(Base):
    __tablename__ = "category_transform_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String(50), index=True)
    level = Column(Integer, nullable=True)
    category = Column(String(255), nullable=False)
    subcategory = Column(String(255), nullable=True)
    sub_subcategory = Column(String(255), nullable=True)
    source_subcategories = Column(JSON, nullable=True)
    target_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
