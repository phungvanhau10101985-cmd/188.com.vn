from typing import List, Optional
from pydantic import BaseModel, Field


class SiteEmbedCodeBase(BaseModel):
    platform: str = Field(..., max_length=32)
    category: str = Field(default="custom", max_length=64)
    title: str = Field(..., max_length=255)
    placement: str = Field(..., description="head | body_open | body_close")
    content: Optional[str] = ""
    hint: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class SiteEmbedCodeCreate(SiteEmbedCodeBase):
    pass


class SiteEmbedCodeUpdate(BaseModel):
    platform: Optional[str] = Field(None, max_length=32)
    category: Optional[str] = Field(None, max_length=64)
    title: Optional[str] = Field(None, max_length=255)
    placement: Optional[str] = None
    content: Optional[str] = None
    hint: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class SiteEmbedCodeResponse(SiteEmbedCodeBase):
    id: int

    class Config:
        from_attributes = True


class PublicSiteEmbedsResponse(BaseModel):
    head: List[str]
    body_open: List[str]
    body_close: List[str]


class SiteEmbedCodeAdminItem(BaseModel):
    """Phản hồi admin: token Conversion API không trả raw content (chỉ secret_configured)."""

    id: int
    platform: str
    category: str
    title: str
    placement: str
    content: str = ""
    hint: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    secret_configured: bool = False

    class Config:
        from_attributes = True


class FacebookCapiEventIn(BaseModel):
    """Gửi sự kiện lên Meta Conversions API từ máy chủ (cần FACEBOOK_CAPI_INGEST_SECRET + đã nhập Pixel + token trong admin)."""

    event_name: str = Field(..., min_length=1, max_length=128)
    event_id: Optional[str] = Field(None, max_length=64, description="Deduplicate với browser Pixel")
    event_time: Optional[int] = Field(None, description="Unix seconds; server gán hiện tại nếu trống")
    action_source: str = Field(default="website")
    custom_data: Optional[dict] = None
    user_data: Optional[dict] = None
