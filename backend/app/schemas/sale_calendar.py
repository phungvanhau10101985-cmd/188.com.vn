from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SiteSaleProductPricing(BaseModel):
    list_price: float = 0
    display_price: float = 0
    savings_amount: float = 0
    percent: float = 0
    phase: Optional[str] = None
    expected_sale_price: Optional[float] = None
    event_label: Optional[str] = None
    event_date: Optional[str] = None
    countdown_to: Optional[str] = None


class SaleCalendarPublicResponse(BaseModel):
    enabled: bool
    phase: Optional[str] = None
    event_date: Optional[str] = None
    event_label: Optional[str] = None
    discount_percent: float = 0
    teaser_days: int = 3
    active_start_at: Optional[str] = None
    active_end_at: Optional[str] = None
    countdown_to: Optional[str] = None
    feed_title_prefix_teaser: str = "Sắp giảm giá"
    feed_title_prefix_active: str = "Đang giảm giá"


class SaleCalendarMonthRuleOut(BaseModel):
    month: int
    enabled: bool
    discount_percent_override: Optional[float] = None
    default_discount_percent: float


class SaleCalendarSettingsOut(BaseModel):
    enabled: bool
    teaser_days: int
    schedule_mode: Literal["auto", "scheduled", "manual"] = "auto"
    scheduled_sale_date: Optional[str] = None
    scheduled_discount_percent: Optional[float] = None
    manual_sale_date: Optional[str] = None
    manual_discount_percent: Optional[float] = None
    warehouse_clearance_enabled: bool = True
    warehouse_clearance_discount_percent: Optional[float] = 20
    month_rules: List[SaleCalendarMonthRuleOut]
    upcoming: List[dict] = Field(default_factory=list)
    current: SaleCalendarPublicResponse


class SaleCalendarSettingsUpdate(BaseModel):
    enabled: Optional[bool] = None
    teaser_days: Optional[int] = Field(None, ge=1, le=14)
    schedule_mode: Optional[Literal["auto", "scheduled", "manual"]] = None
    scheduled_sale_date: Optional[str] = None
    scheduled_discount_percent: Optional[float] = Field(None, ge=0, le=50)
    manual_sale_date: Optional[str] = None
    manual_discount_percent: Optional[float] = Field(None, ge=0, le=50)
    clear_scheduled: bool = False
    clear_manual: bool = False
    warehouse_clearance_enabled: Optional[bool] = None
    warehouse_clearance_discount_percent: Optional[float] = Field(None, ge=0, le=80)


class SaleCalendarMonthRuleUpdate(BaseModel):
    month: int = Field(..., ge=1, le=12)
    enabled: Optional[bool] = None
    discount_percent_override: Optional[float] = Field(None, ge=0, le=50)
