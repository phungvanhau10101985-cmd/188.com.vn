# backend/app/schemas/order.py - ORDER SCHEMAS WITH DEPOSIT
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from decimal import Decimal

class OrderStatus(str, Enum):
    PENDING = "pending"
    WAITING_DEPOSIT = "waiting_deposit"
    DEPOSIT_PAID = "deposit_paid"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPING = "shipping"
    DELIVERED = "delivered"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class PaymentStatus(str, Enum):
    PENDING = "pending"
    DEPOSIT_PAID = "deposit_paid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class PaymentMethod(str, Enum):
    COD = "cod"
    BANK_TRANSFER = "bank_transfer"
    VNPAY = "vnpay"
    MOMO = "momo"
    ZALOPAY = "zalopay"

class DepositType(str, Enum):
    NONE = "none"
    PERCENT_30 = "percent_30"
    PERCENT_100 = "percent_100"

# ========== ORDER ITEM SCHEMAS ==========
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(1, ge=1)
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    selected_color_name: Optional[str] = None

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_slug: Optional[str] = None
    product_name: str
    product_image: Optional[str]
    unit_price: Decimal
    quantity: int
    total_price: Decimal
    selected_size: Optional[str]
    selected_color: Optional[str]
    selected_color_name: Optional[str]
    requires_deposit: bool
    deposit_amount: Decimal
    
    class Config:
        from_attributes = True

# ========== ORDER SCHEMAS ==========
class OrderCreate(BaseModel):
    """Schema for creating order"""
    customer_name: str = Field(..., min_length=2, max_length=255)
    customer_phone: str = Field(..., min_length=10, max_length=20)
    customer_email: EmailStr = Field(..., description="Bắt buộc cho mọi đơn (kể cả khách)")
    customer_address: str = Field(..., min_length=5)
    customer_note: Optional[str] = None
    payment_method: PaymentMethod
    shipping_method: Optional[str] = None
    items: List[OrderItemCreate]
    
    # Deposit information (calculated on backend)
    deposit_type: Optional[DepositType] = None

class OrderUpdate(BaseModel):
    """Schema for updating order (admin only)"""
    status: Optional[OrderStatus] = None
    payment_status: Optional[PaymentStatus] = None
    admin_notes: Optional[str] = None
    tracking_number: Optional[str] = None
    shipping_provider: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    cancelled_reason: Optional[str] = None

class OrderResponse(BaseModel):
    """Order response for users"""
    id: int
    order_code: str
    customer_name: str
    customer_phone: str
    customer_email: Optional[str]
    customer_address: Optional[str] = None  # legacy DB có thể NULL
    customer_note: Optional[str]
    
    # Order amounts
    subtotal: Decimal
    shipping_fee: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    
    # Deposit information
    requires_deposit: bool
    deposit_type: Optional[DepositType]
    deposit_percentage: Optional[int]
    deposit_amount: Decimal
    deposit_paid: Decimal
    remaining_amount: Decimal
    
    # Status
    status: OrderStatus
    payment_method: Optional[PaymentMethod]
    payment_status: PaymentStatus
    
    # Shipping
    shipping_method: Optional[str]
    shipping_provider: Optional[str]
    tracking_number: Optional[str]
    estimated_delivery: Optional[datetime]
    actual_delivery: Optional[datetime]
    
    # Items
    items: List[OrderItemResponse]
    
    # Timestamps
    created_at: Optional[datetime] = None  # DB có thể trả None
    deposit_paid_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    completed_at: Optional[datetime]

    @field_validator("status", "deposit_type", "payment_method", "payment_status", mode="before")
    @classmethod
    def coerce_enum_from_value(cls, v, info):
        """Chấp nhận enum từ model (có .value) hoặc chuỗi để tránh lỗi khi trả order từ SQLAlchemy."""
        if v is None:
            return None
        if isinstance(v, str):
            enum_cls = {"status": OrderStatus, "deposit_type": DepositType, "payment_method": PaymentMethod, "payment_status": PaymentStatus}[info.field_name]
            return enum_cls(v)
        if hasattr(v, "value"):
            enum_cls = {"status": OrderStatus, "deposit_type": DepositType, "payment_method": PaymentMethod, "payment_status": PaymentStatus}[info.field_name]
            return enum_cls(v.value)
        return v
    
    class Config:
        from_attributes = True

# ========== ADMIN ORDER SCHEMAS ==========
class AdminOrderResponse(OrderResponse):
    """Extended order response for admin"""
    user_id: Optional[int]
    processed_by: Optional[int]
    admin_notes: Optional[str]
    cancelled_reason: Optional[str]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class AdminOrderStats(BaseModel):
    """Order statistics for admin dashboard"""
    total_orders: int
    total_revenue: Decimal
    pending_orders: int
    waiting_deposit_orders: int
    deposit_paid_orders: int
    confirmed_orders: int
    processing_orders: int
    shipping_orders: int
    delivered_orders: int
    completed_orders: int
    cancelled_orders: int

# ========== PAYMENT SCHEMAS ==========
class PaymentCreate(BaseModel):
    """Schema for creating payment (deposit)"""
    order_id: int
    amount: Decimal = Field(..., gt=0)
    payment_method: PaymentMethod
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    account_name: Optional[str] = None
    transaction_code: Optional[str] = None
    transfer_date: Optional[datetime] = None

class PaymentConfirm(BaseModel):
    """Schema for admin to confirm payment"""
    payment_id: int
    is_confirmed: bool = True
    confirmation_note: Optional[str] = None

class PaymentResponse(BaseModel):
    """Payment response"""
    id: int
    payment_code: str
    order_id: int
    amount: Decimal
    payment_method: PaymentMethod
    payment_type: str
    payment_status: PaymentStatus
    bank_name: Optional[str]
    transaction_code: Optional[str]
    confirmed_by: Optional[int]
    confirmed_at: Optional[datetime]
    created_at: Optional[datetime] = None  # DB có thể trả None
    
    class Config:
        from_attributes = True


class SepayDepositInfoResponse(BaseModel):
    """QR SePay + nội dung CK cho trang đặt cọc."""

    enabled: bool
    transfer_content: str
    amount: Decimal
    qr_image_url: Optional[str] = None
    bank_code: Optional[str] = None
    account_number: Optional[str] = None
    register_webhook_url: Optional[str] = None