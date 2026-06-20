"""Hàng đợi email phản hồi câu hỏi/đánh giá — debounce qua DB (ổn định đa worker)."""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class PendingProductReplyEmail(Base):
    __tablename__ = "pending_product_reply_emails"
    __table_args__ = (
        UniqueConstraint("kind", "entity_id", "slot", name="uq_pending_product_reply_email"),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)  # question | review
    entity_id = Column(Integer, nullable=False, index=True)
    slot = Column(String(20), nullable=False, default="")
    send_after = Column(DateTime(timezone=True), nullable=False, index=True)
    exclude_replier_user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ProductReplyEmailSentLog(Base):
    """Tránh gửi lại cùng nội dung trong cửa sổ ngắn."""

    __tablename__ = "product_reply_email_sent_logs"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    slot = Column(String(20), nullable=False, default="")
    content_fingerprint = Column(String(64), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
