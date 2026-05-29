from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class NewsletterSubscriber(Base):
    __tablename__ = "newsletter_subscribers"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    source = Column(String(50), nullable=False, default="footer")
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    # Khách import (file cột name, gender, birthday, phone)
    subscriber_name = Column(String(255), nullable=True)
    gender = Column(String(20), nullable=True)
    birthday = Column(Date, nullable=True)
    phone = Column(String(20), nullable=True, index=True)
    email_original = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", lazy="joined")
