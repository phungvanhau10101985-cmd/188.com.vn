"""Sổ lượt gọi model AI — token, chức năng, độ phân giải ảnh."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class ApiUsageLog(Base):
    __tablename__ = "api_usage_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    model = Column(String(160), nullable=False, index=True)
    feature = Column(String(80), nullable=False, index=True)
    prompt_token_count = Column(Integer, nullable=False, default=0)
    candidates_token_count = Column(Integer, nullable=False, default=0)
    total_token_count = Column(Integer, nullable=False, default=0)
    image_size = Column(String(8), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
