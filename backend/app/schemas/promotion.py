from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class PromoValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    subtotal: Optional[Decimal] = Field(default=None, ge=0)


class PromotionVoucherItem(BaseModel):
    grant_id: Optional[int] = None
    code: str
    name: str
    description: Optional[str] = None
    discount_percent: float
    max_discount_amount: float
    eligible: bool
    reason: Optional[str] = None
    eligible_within_days: Optional[int] = None
    show_days_remaining: bool = False
    days_remaining: Optional[int] = None
    expires_at: Optional[str] = None
    granted_at: Optional[str] = None
    source: Optional[str] = None
    is_new: bool = False
    estimated_discount: Optional[float] = None


class PromotionVoucherListResponse(BaseModel):
    items: List[PromotionVoucherItem] = []


class WelcomeEligibilityResponse(BaseModel):
    eligible: bool
    code: str = "WELCOME188"
    name: str = "Chào mừng khách mới"
    description: Optional[str] = None
    discount_percent: float = 10.0
    max_discount_amount: float = 200000.0
    eligible_within_days: Optional[int] = None
    show_days_remaining: bool = False
    days_remaining: Optional[int] = None
    expires_at: Optional[str] = None
    reason: Optional[str] = None
    is_active: bool = True


class PromoValidateResponse(BaseModel):
    valid: bool
    code: str
    discount_percent: float
    max_discount_amount: float
    estimated_discount: float = 0.0
    message: str


class AdminWelcomePromoOut(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    discount_percent: float
    max_discount_amount: float
    eligible_within_days: Optional[int] = None
    show_days_remaining: bool = False
    is_active: bool
    first_order_only: bool = True

    class Config:
        from_attributes = True


class AdminWelcomePromoUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    max_discount_amount: Optional[float] = Field(None, ge=0)
    eligible_within_days: Optional[int] = Field(
        None,
        ge=0,
        le=365,
        description="Số ngày hiệu lực mã sau khi tặng vào ví.",
    )
    is_active: Optional[bool] = None


class AdminGrantVoucherRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    promo_code: str = Field(..., min_length=1, max_length=50)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    message: Optional[str] = None
    notify: bool = True


class AdminGrantSegmentRequest(BaseModel):
    segment: str = Field(..., description="comeback | welcome_backfill | cart_abandon")
    inactive_days: Optional[int] = Field(30, ge=7, le=180)
    abandon_hours: Optional[int] = Field(24, ge=6, le=168)


class AdminGrantSegmentResponse(BaseModel):
    granted: int
    skipped: int
    emails_sent: int = 0


class AdminDailyPromotionCronResponse(BaseModel):
    voucher_grants: dict
    birthday_emails: Optional[dict] = None


class AdminUserGrantOut(BaseModel):
    id: int
    user_id: int
    code: str
    name: str
    status: str
    source: str
    granted_at: Optional[str] = None
    expires_at: Optional[str] = None


class AdminPromotionOut(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    discount_percent: float
    max_discount_amount: Optional[float] = None
    first_order_only: bool
    stack_with_birthday: bool
    stack_with_loyalty: bool
    is_active: bool
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    usage_limit: Optional[int] = None
    per_user_limit: int
    eligible_within_days: Optional[int] = None
    grant_valid_days: Optional[int] = None
    requires_wallet_grant: bool
    auto_grant_trigger: str
    grants_count: int = 0
    usages_count: int = 0
    is_system_template: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AdminPromotionCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    discount_percent: float = Field(..., ge=0, le=100)
    max_discount_amount: Optional[float] = Field(None, ge=0)
    first_order_only: bool = True
    stack_with_birthday: bool = False
    stack_with_loyalty: bool = True
    is_active: bool = True
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    per_user_limit: int = Field(1, ge=1, le=100)
    eligible_within_days: Optional[int] = Field(None, ge=0, le=365)
    grant_valid_days: Optional[int] = Field(None, ge=1, le=365)
    requires_wallet_grant: bool = True
    auto_grant_trigger: str = Field("none", max_length=50)


class AdminPromotionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    max_discount_amount: Optional[float] = Field(None, ge=0)
    first_order_only: Optional[bool] = None
    stack_with_birthday: Optional[bool] = None
    stack_with_loyalty: Optional[bool] = None
    is_active: Optional[bool] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    usage_limit: Optional[int] = Field(None, ge=1)
    per_user_limit: Optional[int] = Field(None, ge=1, le=100)
    eligible_within_days: Optional[int] = Field(None, ge=0, le=365)
    grant_valid_days: Optional[int] = Field(None, ge=1, le=365)
    requires_wallet_grant: Optional[bool] = None
    auto_grant_trigger: Optional[str] = Field(None, max_length=50)


class AdminPromotionListResponse(BaseModel):
    items: List[AdminPromotionOut] = []
