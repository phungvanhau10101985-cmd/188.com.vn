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


class EmsTrackingEventResponse(BaseModel):
    status_code: Optional[int] = None
    description: str
    address: Optional[str] = None
    traced_at: Optional[datetime] = None


class EmsTrackingResponse(BaseModel):
    available: bool = False
    tracking_code: Optional[str] = None
    current_status: Optional[int] = None
    current_status_description: Optional[str] = None
    events: List[EmsTrackingEventResponse] = []
    error: Optional[str] = None


class OrderShipmentTimelineResponse(BaseModel):
    order_id: int
    order_code: str
    order_status: str
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    footer_note: str
    current_step_key: Optional[str] = None
    waiting_admin_at_customs: bool = False
    waiting_admin_domestic_delivery: bool = False
    can_confirm_received: bool = False
    events: List[ShipmentEventResponse]
    ems_tracking: Optional[EmsTrackingResponse] = None


class AdminClearCustomsIn(BaseModel):
    pass


class AdminMarkOutForConfirmIn(BaseModel):
    tracking_number: Optional[str] = Field(default=None, max_length=100)
    shipping_provider: Optional[str] = Field(default=None, max_length=100)


class EmsShippingImportRowResponse(BaseModel):
    row_number: int
    reference_code: str
    recipient_label: str
    order_code: Optional[str] = None
    order_id: Optional[int] = None
    order_status: Optional[str] = None
    current_step_key: Optional[str] = None
    tracking_number_saved: Optional[str] = None
    ems_tracking_code: Optional[str] = None
    ems_reference_code: Optional[str] = None
    ems_status: Optional[str] = None
    ems_phase: Optional[str] = None
    sync_status: str
    sync_message: str
    ems_error: Optional[str] = None


class EmsShippingImportSummaryResponse(BaseModel):
    total_rows: int
    matched: int
    in_progress: int
    mismatch: int
    order_not_found: int
    ems_not_found: int
    parse_error: int


class EmsShippingImportResponse(BaseModel):
    ok: bool = True
    warnings: List[str] = []
    summary: EmsShippingImportSummaryResponse
    rows: List[EmsShippingImportRowResponse]
