from typing import Literal, Optional

from pydantic import BaseModel, Field


class MarketingIconCurrentResponse(BaseModel):
    icon_url: str
    default_icon_url: str
    is_sale: bool = False
    kind: Optional[Literal["sale"]] = None
    campaign_key: Optional[str] = None
    date_key: Optional[str] = None
    discount_percent: Optional[float] = None
    event_date: Optional[str] = None
    event_label: Optional[str] = None
    phase: Optional[str] = None
    version: Optional[int] = None


class MarketingIconAdminItem(BaseModel):
    id: int
    kind: str
    campaign_key: str
    date_key: str
    discount_percent: float
    image_url: Optional[str] = None
    source_image_url: Optional[str] = None
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


class MarketingIconAdminListResponse(BaseModel):
    items: list[MarketingIconAdminItem] = []


class MarketingIconRegenerateRequest(BaseModel):
    kind: Literal["sale"] = "sale"
    day: int = Field(..., ge=1, le=31)
    month: int = Field(..., ge=1, le=12)
