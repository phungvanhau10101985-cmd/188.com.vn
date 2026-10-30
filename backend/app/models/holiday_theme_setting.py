# Chủ đề ngày lễ storefront (singleton id=1). active_theme null = giao diện thường.
from sqlalchemy import Column, DateTime, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.base import Base
from app.db.coerced_date import CoercedDate


class HolidayThemeSetting(Base):
    __tablename__ = "holiday_theme_settings"

    id = Column(Integer, primary_key=True, index=True)
    active_theme = Column(String(32), nullable=True)
    starts_on = Column(CoercedDate, nullable=True)
    ends_on = Column(CoercedDate, nullable=True)
    lead_days = Column(Integer, nullable=False, default=0, server_default="0")
    after_days = Column(Integer, nullable=False, default=0, server_default="0")
    sale_percent = Column(Numeric(5, 2), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<HolidayThemeSetting id={self.id} active_theme={self.active_theme!r}>"
