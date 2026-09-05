from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketingBannerItem(BaseModel):
    id: int
    kind: Literal["sale", "birthday"]
    campaign_key: str
    date_key: str
    discount_percent: float
    image_url: str
    aspect_ratio: str = "21:9"
    event_date: Optional[str] = None
    greeting: Optional[str] = None
    version: int


class MarketingBannerCurrentResponse(BaseModel):
    items: list[MarketingBannerItem] = []


class MarketingBannerAdminItem(BaseModel):
    id: int
    kind: str
    campaign_key: str
    date_key: str
    discount_percent: float
    image_url: Optional[str] = None
    aspect_ratio: str
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    prompt: str
    provider: str
    model: str
    status: str
    error_message: Optional[str] = None
    version: int
    is_active: bool
    generated_at: Optional[str] = None
    created_at: Optional[str] = None


class MarketingBannerAdminListResponse(BaseModel):
    items: list[MarketingBannerAdminItem] = []


class MarketingBannerRegenerateRequest(BaseModel):
    kind: Literal["sale", "birthday"]
    day: int = Field(..., ge=1, le=31)
    month: int = Field(..., ge=1, le=12)
