"""Khóa đọc chi phí Google Ads và Facebook Ads — một dòng cấu hình."""

from sqlalchemy import Column, DateTime, Integer, Text
from sqlalchemy.sql import func

from app.db.base import Base


class AdSpendSettings(Base):
    __tablename__ = "ad_spend_settings"

    id = Column(Integer, primary_key=True, default=1)
    google_developer_token = Column(Text, nullable=True)
    google_client_id = Column(Text, nullable=True)
    google_client_secret = Column(Text, nullable=True)
    google_refresh_token = Column(Text, nullable=True)
    google_customer_id = Column(Text, nullable=True)
    google_login_customer_id = Column(Text, nullable=True)
    meta_access_token = Column(Text, nullable=True)
    meta_ad_account_id = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
