"""Lỗi web + log server, gom theo ngày (giờ Việt Nam) để admin xem và gửi email."""

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class SiteErrorLog(Base):
    __tablename__ = "site_error_logs"
    __table_args__ = (
        UniqueConstraint("fingerprint", "log_day", "source", name="uq_site_error_fp_day_source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    fingerprint = Column(String(64), nullable=False, index=True)
    log_day = Column(Date, nullable=False, index=True)
    source = Column(String(20), nullable=False, index=True)  # server | web | web_server
    level = Column(String(20), nullable=False, default="error")
    logger_name = Column(String(160), nullable=True)
    exc_type = Column(String(160), nullable=True)
    message = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    path = Column(String(500), nullable=True)
    method = Column(String(12), nullable=True)
    status_code = Column(Integer, nullable=True)
    user_agent = Column(String(300), nullable=True)
    client_ip = Column(String(64), nullable=True)
    occurrence_count = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
