from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class AffiliateMeResponse(BaseModel):
    referral_code: str
    referral_link: str
    referred_by_user_id: Optional[int] = None
    balance: Decimal
    pending_balance: Decimal
    affiliate_enabled: bool = True
    commission_percent: float
    min_withdrawal: Decimal
    ref_cookie_days: int = 30
    commission_policy: Optional[str] = None
    affiliate_status: str = "not_applied"
    affiliate_application: Optional[dict] = None
    total_commissions_confirmed: Decimal
    total_commissions_pending: Decimal
    total_orders_referred: int


class AffiliateAttributeIn(BaseModel):
    referral_code: str = Field(..., min_length=3, max_length=32)


class AffiliateApplicationIn(BaseModel):
    social_links: List[str] = Field(..., min_length=1, max_length=10)
    note: Optional[str] = Field(default=None, max_length=1000)


class AffiliateApplicationResponse(BaseModel):
    id: int
    user_id: int
    user_email: Optional[str] = None
    status: str
    social_links: List[str]
    note: Optional[str] = None
    admin_note: Optional[str] = None
    reviewed_by: Optional[int] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminAffiliateApplicationDecisionIn(BaseModel):
    admin_note: Optional[str] = Field(default=None, max_length=1000)


class WalletTransactionResponse(BaseModel):
    id: int
    tx_type: str
    tx_type_label: Optional[str] = None
    amount: Decimal
    balance_after: Decimal
    pending_after: Decimal
    description: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    order_code: Optional[str] = None
    order_status: Optional[str] = None
    order_status_label: Optional[str] = None
    product_summary: Optional[str] = None
    affects_bucket: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserBankAccountIn(BaseModel):
    bank_name: str = Field(..., min_length=2, max_length=120)
    bank_account: str = Field(..., min_length=4, max_length=40)
    account_holder: str = Field(..., min_length=2, max_length=255)


class UserBankAccountOtpRequest(UserBankAccountIn):
    pass


class UserBankAccountVerifyIn(UserBankAccountIn):
    otp: str = Field(..., min_length=4, max_length=8)


class BankAccountOtpResponse(BaseModel):
    ok: bool = True
    email: str
    expires_in_minutes: int
    message: str


class UserBankAccountResponse(UserBankAccountIn):
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WalletWithdrawIn(BaseModel):
    amount: Decimal = Field(..., gt=0)


class WalletWithdrawalResponse(BaseModel):
    id: int
    user_id: int
    amount: Decimal
    bank_name: str
    bank_account: str
    account_holder: str
    status: str
    admin_note: Optional[str] = None
    created_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminAffiliateCommissionResponse(BaseModel):
    id: int
    referrer_user_id: int
    buyer_user_id: Optional[int] = None
    order_id: int
    order_base_amount: Decimal
    commission_percent: Decimal
    commission_amount: Decimal
    status: str
    created_at: datetime
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminWithdrawRejectIn(BaseModel):
    admin_note: Optional[str] = None


class AffiliateReferredOrderResponse(BaseModel):
    order_id: int
    order_code: Optional[str] = None
    buyer_label: str
    buyer_name: str = ""
    buyer_phone: str = ""
    buyer_address: str = ""
    product_summary: str
    order_total: Decimal
    order_status: str
    order_status_label: str
    commission_amount: Decimal
    commission_percent: float
    commission_status: str
    commission_status_label: str
    withdrawable: bool
    order_created_at: datetime
    commission_created_at: Optional[datetime] = None
    commission_confirmed_at: Optional[datetime] = None


class AffiliateSettingsResponse(BaseModel):
    id: int
    enabled: bool
    commission_percent: Decimal
    min_withdrawal: Decimal
    ref_cookie_days: int
    commission_policy: Optional[str] = None
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AffiliateSettingsUpdate(BaseModel):
    enabled: bool = True
    commission_percent: Decimal = Field(..., ge=0, le=100)
    min_withdrawal: Decimal = Field(..., ge=0)
    ref_cookie_days: int = Field(..., ge=1, le=365)
    commission_policy: Optional[str] = Field(default=None, max_length=2000)
