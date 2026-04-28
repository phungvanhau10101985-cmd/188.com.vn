from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

class NotificationBase(BaseModel):
    title: str
    content: str
    type: Optional[str] = "general"
    scheduled_at: Optional[datetime] = None

class NotificationCreate(NotificationBase):
    user_id: int
    expires_at: Optional[datetime] = None

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None

class NotificationResponse(NotificationBase):
    id: int
    user_id: int
    is_read: bool
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class NotificationImportRow(BaseModel):
    phone: str
    title: str
    content: str
    time_will_send: str # Format: 15/1/2022 15:30:00

class NotificationImportResponse(BaseModel):
    total_processed: int
    success_count: int
    error_count: int
    errors: List[str]
