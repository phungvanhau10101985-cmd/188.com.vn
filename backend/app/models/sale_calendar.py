from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.db.base import Base
from app.db.coerced_date import CoercedDate


class SaleCalendarSettings(Base):
    """Cài đặt chung chương trình sale ngày trùng tháng (1 hàng id=1)."""

    __tablename__ = "sale_calendar_settings"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    teaser_days = Column(Integer, nullable=False, default=3)
    # auto: lịch ngày trùng tháng hàng tháng | scheduled: một ngày đặt sẵn | manual: sale thủ công hôm nay
    schedule_mode = Column(String(20), nullable=False, default="auto")
    scheduled_sale_date = Column(CoercedDate, nullable=True)
    scheduled_discount_percent = Column(Numeric(5, 2), nullable=True)
    manual_sale_date = Column(CoercedDate, nullable=True)
    manual_discount_percent = Column(Numeric(5, 2), nullable=True)


class SaleCalendarMonthRule(Base):
    """Quy tắc theo tháng (1–12): bật/tắt và override % giảm."""

    __tablename__ = "sale_calendar_month_rules"

    month = Column(Integer, primary_key=True)  # 1..12
    enabled = Column(Boolean, nullable=False, default=True)
    discount_percent_override = Column(Numeric(5, 2), nullable=True)
