from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class BirthdayPromoEmailLog(Base):
    __tablename__ = "birthday_promo_email_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "campaign_key", name="uq_birthday_promo_user_campaign"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_key = Column(String(32), nullable=False, index=True)
    birthday_date = Column(Date, nullable=False)
    recipient_email = Column(String(255), nullable=False)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
