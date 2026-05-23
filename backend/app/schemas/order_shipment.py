from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ShipmentEventResponse(BaseModel):
    step_key: str
    title: str
    status: str
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    note: Optional[str] = None


class OrderShipmentTimelineResponse(BaseModel):
    order_id: int
    order_code: str
    order_status: str
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    footer_note: str
    current_step_key: Optional[str] = None
    waiting_admin_at_customs: bool = False
    events: List[ShipmentEventResponse]


class AdminClearCustomsIn(BaseModel):
    tracking_number: Optional[str] = Field(default=None, max_length=100)
    shipping_provider: Optional[str] = Field(default=None, max_length=100)
