from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class MarketingEmailSuppression(Base):
    """Email đã bấm ngừng nhận tin khuyến mãi (giỏ bỏ dở, nhớ bạn, CMSN, campaign)."""

    __tablename__ = "marketing_email_suppressions"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    source = Column(String(50), nullable=False, default="unsubscribe_link")
    unsubscribed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
