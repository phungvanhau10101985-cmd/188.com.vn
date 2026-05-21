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
from sqlalchemy.sql import func

from app.db.base import Base


class AffiliateSettings(Base):
    __tablename__ = "affiliate_settings"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    commission_percent = Column(Numeric(5, 2), nullable=False, default=10)
    min_withdrawal = Column(Numeric(12, 2), nullable=False, default=100000)
    ref_cookie_days = Column(Integer, nullable=False, default=30)
    commission_policy = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AffiliateProfile(Base):
    __tablename__ = "affiliate_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    referral_code = Column(String(32), nullable=False, unique=True, index=True)
    referred_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referred_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AffiliateApplication(Base):
    __tablename__ = "affiliate_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    social_links = Column(Text, nullable=False, default="[]")
    note = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserWallet(Base):
    __tablename__ = "user_wallets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    balance = Column(Numeric(12, 2), nullable=False, default=0)
    pending_balance = Column(Numeric(12, 2), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tx_type = Column(String(40), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    balance_after = Column(Numeric(12, 2), nullable=False, default=0)
    pending_after = Column(Numeric(12, 2), nullable=False, default=0)
    reference_type = Column(String(40), nullable=True)
    reference_id = Column(Integer, nullable=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class AffiliateCommission(Base):
    __tablename__ = "affiliate_commissions"
    __table_args__ = (UniqueConstraint("order_id", name="uq_affiliate_commission_order"),)

    id = Column(Integer, primary_key=True, index=True)
    referrer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    order_base_amount = Column(Numeric(12, 2), nullable=False, default=0)
    commission_percent = Column(Numeric(5, 2), nullable=False, default=0)
    commission_amount = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class UserBankAccount(Base):
    __tablename__ = "user_bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    bank_name = Column(String(120), nullable=False)
    bank_account = Column(String(40), nullable=False)
    account_holder = Column(String(255), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AffiliateBankAccountOtp(Base):
    __tablename__ = "affiliate_bank_account_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    otp_hash = Column(String(64), nullable=False)
    payload_hash = Column(String(64), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WalletWithdrawal(Base):
    __tablename__ = "wallet_withdrawals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    bank_name = Column(String(120), nullable=False)
    bank_account = Column(String(40), nullable=False)
    account_holder = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    admin_note = Column(Text, nullable=True)
    processed_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
