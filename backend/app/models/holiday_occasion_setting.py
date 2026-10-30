"""Một dịp lễ. Ngày/tháng lặp mỗi năm, không lưu năm."""
from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.db.base import Base


class HolidayOccasionSetting(Base):
    __tablename__ = "holiday_occasion_settings"

    code = Column(String(32), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=True)
    start_month = Column(Integer, nullable=False)
    start_day = Column(Integer, nullable=False)
    end_month = Column(Integer, nullable=False)
    end_day = Column(Integer, nullable=False)
    lead_days = Column(Integer, nullable=False, default=0)
    after_days = Column(Integer, nullable=False, default=0)
    sale_percent = Column(Numeric(5, 2), nullable=True)
