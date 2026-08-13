"""Schemas cổng API tra cứu vận chuyển (partner / tích hợp)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ShippingLookupRequest(BaseModel):
    q: Optional[str] = Field(
        default=None,
        max_length=80,
        description="Một giá trị: mã đơn web (DH001), SĐT khách, hoặc mã EMS (EH…VN)",
    )
    order_code: Optional[str] = Field(default=None, max_length=50, description="Mã đơn web, vd. DH042")
    phone: Optional[str] = Field(default=None, max_length=20, description="Số điện thoại khách — trả đơn gần nhất")
    ems_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Mã vận đơn EMS — trả chi tiết đơn + hành trình EMS đầy đủ",
    )


class ShippingLookupItemResponse(BaseModel):
    product_id: int
    product_name: str
    product_image: Optional[str] = None
    product_slug: Optional[str] = None
    product_code: Optional[str] = None
    product_sku: Optional[str] = None
    unit_price: float = 0
    quantity: int = 0
    total_price: float = 0
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    selected_color_name: Optional[str] = None


class ShippingLookupOrderResponse(BaseModel):
    id: int
    order_code: str
    status: str
    status_label: str
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    payment_status_label: Optional[str] = None
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    customer_note: Optional[str] = None
    shipping_method: Optional[str] = None
    shipping_provider: Optional[str] = None
    tracking_number: Optional[str] = None
    subtotal: float = 0
    shipping_fee: float = 0
    discount_amount: float = 0
    wallet_amount_used: float = 0
    total_amount: float = 0
    requires_deposit: bool = False
    deposit_amount: float = 0
    deposit_paid: float = 0
    remaining_amount: float = 0
    estimated_delivery: Optional[datetime] = None
    actual_delivery: Optional[datetime] = None
    created_at: Optional[datetime] = None
    deposit_paid_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    items: List[ShippingLookupItemResponse] = []


class ShippingLookupTimelineEventResponse(BaseModel):
    step_key: str
    title: str
    status: str
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    note: Optional[str] = None


class ShippingLookupShopTimelineResponse(BaseModel):
    current_step_key: Optional[str] = None
    footer_note: Optional[str] = None
    waiting_admin_at_customs: bool = False
    waiting_admin_domestic_delivery: bool = False
    events: List[ShippingLookupTimelineEventResponse] = []


class ShippingLookupEmsEventResponse(BaseModel):
    status_code: Optional[int] = None
    description: str
    address: Optional[str] = None
    traced_at: Optional[datetime] = None


class ShippingLookupEmsTrackingResponse(BaseModel):
    available: bool = False
    tracking_code: Optional[str] = None
    reference_code: Optional[str] = None
    customer_code: Optional[str] = None
    weight_grams: Optional[str] = None
    receiver_address: Optional[str] = None
    current_status: Optional[int] = None
    current_status_description: Optional[str] = None
    events: List[ShippingLookupEmsEventResponse] = []
    error: Optional[str] = None


class ShippingLookupEmsRecordResponse(BaseModel):
    reference_code: Optional[str] = None
    ems_tracking_code: Optional[str] = None
    ems_reference_code: Optional[str] = None
    ems_status: Optional[str] = None
    ems_phase: Optional[str] = None
    ems_phase_label: Optional[str] = None
    sync_status: Optional[str] = None
    sync_message: Optional[str] = None
    product_code: Optional[str] = None
    recipient_label: Optional[str] = None
    cod_amount: Optional[float] = None
    cod_paid_amount: Optional[float] = None
    cod_paid_date: Optional[str] = None
    cod_settlement_status: Optional[str] = None
    freight_amount: Optional[float] = None
    freight_settlement_status: Optional[str] = None
    shop_return_received_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ShippingLookupResponse(BaseModel):
    ok: bool = True
    query: str
    query_type: str = Field(description="order_code | phone | ems_code")
    matched_by: Optional[str] = None
    is_latest_order: bool = False
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    order: Optional[ShippingLookupOrderResponse] = None
    shop_timeline: Optional[ShippingLookupShopTimelineResponse] = None
    ems_record: Optional[ShippingLookupEmsRecordResponse] = None
    ems_tracking: Optional[ShippingLookupEmsTrackingResponse] = None
