from typing import Optional, List
from pydantic import BaseModel
from decimal import Decimal

# Shared properties
class LoyaltyTierBase(BaseModel):
    name: Optional[str] = None
    min_spend: Optional[Decimal] = None
    discount_percent: Optional[float] = None
    description: Optional[str] = None

# Properties to receive via API on creation
class LoyaltyTierCreate(LoyaltyTierBase):
    name: str
    min_spend: Decimal
    discount_percent: float

# Properties to receive via API on update
class LoyaltyTierUpdate(LoyaltyTierBase):
    pass

class LoyaltyTierInDBBase(LoyaltyTierBase):
    id: int

    class Config:
        orm_mode = True

# Additional properties to return via API
class LoyaltyTier(LoyaltyTierInDBBase):
    pass

# Schema for User's Loyalty Status
class UserLoyaltyStatus(BaseModel):
    current_tier: Optional[LoyaltyTier] = None
    total_spent_6_months: Decimal
    next_tier: Optional[LoyaltyTier] = None
    remaining_spend_for_next_tier: Optional[Decimal] = None
    message: Optional[str] = None
