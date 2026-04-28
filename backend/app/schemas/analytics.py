from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class AnalyticsEventCreate(BaseModel):
    event_name: str = Field(..., description="Tên sự kiện")
    session_id: Optional[str] = Field(None, description="Session ID phía client")
    page_url: Optional[str] = Field(None, description="URL hiện tại")
    referrer: Optional[str] = Field(None, description="Trang giới thiệu")
    properties: Optional[Dict[str, Any]] = Field(None, description="Thuộc tính bổ sung")


class AnalyticsEventResponse(AnalyticsEventCreate):
    id: int
    user_id: Optional[int] = None
    user_agent: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
