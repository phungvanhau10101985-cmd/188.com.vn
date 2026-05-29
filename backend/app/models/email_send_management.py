from sqlalchemy import Boolean, Column, Date, DateTime, Integer
from sqlalchemy.sql import func

from app.db.base import Base


class EmailSendManagement(Base):
    """Singleton (id=1): cài đặt warm-up và đếm gửi email theo ngày."""

    __tablename__ = "email_send_management"

    id = Column(Integer, primary_key=True, index=True)

    warmup_enabled = Column(Boolean, nullable=False, default=True)
    start_limit = Column(Integer, nullable=False, default=5)
    daily_increment = Column(Integer, nullable=False, default=5)
    max_limit = Column(Integer, nullable=True)

    birthday_cron_enabled = Column(Boolean, nullable=False, default=True)

    warmup_started_at = Column(DateTime(timezone=True), nullable=True)
    warmup_day = Column(Integer, nullable=False, default=1)
    daily_sent_total = Column(Integer, nullable=False, default=0)
    daily_birthday_sent = Column(Integer, nullable=False, default=0)
    daily_marketing_sent = Column(Integer, nullable=False, default=0)
    last_reset_date = Column(Date, nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
