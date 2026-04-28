from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.db.base import Base


class SearchLog(Base):
    __tablename__ = "search_logs"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(500), index=True, nullable=False)
    result_count = Column(Integer, default=0)
    ai_processed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
