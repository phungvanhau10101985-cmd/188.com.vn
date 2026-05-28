from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.db.base import Base


class AdminFeatureTestSetting(Base):
    __tablename__ = "admin_feature_test_settings"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    test_email = Column(String(255), nullable=True, index=True)
    birthday_promo_enabled = Column(Boolean, default=False, nullable=False)
    birthday_promo_expires_at = Column(DateTime(timezone=True), nullable=True)
    site_sale_test_enabled = Column(Boolean, default=False, nullable=False)
    site_sale_test_expires_at = Column(DateTime(timezone=True), nullable=True)
    site_sale_test_phase = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
