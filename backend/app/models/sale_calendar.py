from sqlalchemy import Boolean, Column, Integer, Numeric

from app.db.base import Base


class SaleCalendarSettings(Base):
    """Cài đặt chung chương trình sale ngày trùng tháng (1 hàng id=1)."""

    __tablename__ = "sale_calendar_settings"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    teaser_days = Column(Integer, nullable=False, default=3)


class SaleCalendarMonthRule(Base):
    """Quy tắc theo tháng (1–12): bật/tắt và override % giảm."""

    __tablename__ = "sale_calendar_month_rules"

    month = Column(Integer, primary_key=True)  # 1..12
    enabled = Column(Boolean, nullable=False, default=True)
    discount_percent_override = Column(Numeric(5, 2), nullable=True)
