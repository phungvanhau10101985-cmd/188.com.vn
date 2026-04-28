from sqlalchemy import Column, Integer, String, DateTime, Enum, func
from enum import Enum as PyEnum
from app.db.base import Base


class SearchMappingType(PyEnum):
    product_search = "product_search"
    category_redirect = "category_redirect"


class SearchMapping(Base):
    __tablename__ = "search_mappings"

    id = Column(Integer, primary_key=True, index=True)
    keyword_input = Column(String(500), unique=True, index=True, nullable=False)
    keyword_target = Column(String(500), nullable=False)
    type = Column(Enum(SearchMappingType), nullable=False, default=SearchMappingType.product_search)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
