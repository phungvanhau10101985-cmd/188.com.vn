import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class GrantStatus(enum.Enum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"


class AutoGrantTrigger(enum.Enum):
    NONE = "none"
    SIGNUP = "signup"
    FIRST_DELIVERED = "first_delivered"
    COMEBACK = "comeback"
    CART_ABANDON = "cart_abandon"


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    max_discount_amount = Column(Numeric(12, 2), nullable=True)
    first_order_only = Column(Boolean, default=True, nullable=False)
    stack_with_birthday = Column(Boolean, default=False, nullable=False)
    stack_with_loyalty = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    usage_limit = Column(Integer, nullable=True)
    per_user_limit = Column(Integer, default=1, nullable=False)
    eligible_within_days = Column(Integer, nullable=True)
    requires_wallet_grant = Column(Boolean, default=True, nullable=False)
    grant_valid_days = Column(Integer, nullable=True)
    auto_grant_trigger = Column(String(50), default="none", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserPromotionGrant(Base):
    __tablename__ = "user_promotion_grants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False, index=True)
    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(50), nullable=False, default="admin")
    status = Column(String(20), default="active", nullable=False, index=True)
    used_order_id = Column(Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    grant_message = Column(Text, nullable=True)

    promotion = relationship("Promotion", lazy="joined")
    user = relationship("User", lazy="joined")


class PromotionUsage(Base):
    __tablename__ = "promotion_usages"
    __table_args__ = (
        UniqueConstraint("promotion_id", "order_id", name="uq_promotion_usages_promotion_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    grant_id = Column(Integer, ForeignKey("user_promotion_grants.id", ondelete="SET NULL"), nullable=True)
    discount_amount = Column(Numeric(12, 2), nullable=False, default=0)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
