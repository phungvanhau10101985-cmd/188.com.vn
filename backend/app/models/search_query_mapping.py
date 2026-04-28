from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base


class SearchQueryMapping(Base):
    __tablename__ = "search_query_mappings"

    id = Column(Integer, primary_key=True, index=True)
    normalized_key = Column(String(500), unique=True, index=True, nullable=False)
    raw_query = Column(String(500), nullable=False)
    corrected_query = Column(String(500), nullable=False)
    result_count = Column(Integer, default=0)
    used_count = Column(Integer, default=0)
    source = Column(String(50), default="gemini")
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
