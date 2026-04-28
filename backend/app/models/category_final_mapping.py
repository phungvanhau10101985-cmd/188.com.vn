from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class CategoryFinalMapping(Base):
    __tablename__ = "category_final_mappings"

    id = Column(Integer, primary_key=True, index=True)
    from_category = Column(String(255), nullable=False, index=True)
    from_subcategory = Column(String(255), nullable=True, index=True)
    from_sub_subcategory = Column(String(255), nullable=True, index=True)
    to_category = Column(String(255), nullable=False)
    to_subcategory = Column(String(255), nullable=True)
    to_sub_subcategory = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
