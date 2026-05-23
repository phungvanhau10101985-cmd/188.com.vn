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
