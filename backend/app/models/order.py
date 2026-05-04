# backend/app/models/order.py - COMPLETE WITH FIXED RELATIONSHIPS
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text, Float, ForeignKey, JSON, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.db.base import Base

class OrderStatus(enum.Enum):
    PENDING = "pending"              # Chờ xác nhận
    WAITING_DEPOSIT = "waiting_deposit"  # Chờ đặt cọc
    DEPOSIT_PAID = "deposit_paid"    # Đã đặt cọc
    CONFIRMED = "confirmed"          # Đã xác nhận
    PROCESSING = "processing"        # Đang xử lý
    SHIPPING = "shipping"            # Đang giao hàng
    DELIVERED = "delivered"          # Đã giao hàng
    COMPLETED = "completed"          # Đã hoàn thành (đã đánh giá)
    CANCELLED = "cancelled"          # Đã hủy

class PaymentMethod(enum.Enum):
    COD = "cod"                      # Thanh toán khi nhận hàng
    BANK_TRANSFER = "bank_transfer"  # Chuyển khoản ngân hàng
    VNPAY = "vnpay"
    MOMO = "momo"
    ZALOPAY = "zalopay"

class PaymentStatus(enum.Enum):
    PENDING = "pending"              # Chờ thanh toán
    DEPOSIT_PAID = "deposit_paid"    # Đã đặt cọc
    PARTIALLY_PAID = "partially_paid" # Đã thanh toán một phần
    PAID = "paid"                    # Đã thanh toán đủ
    FAILED = "failed"                # Thanh toán thất bại
    REFUNDED = "refunded"            # Đã hoàn tiền

class DepositType(enum.Enum):
    NONE = "none"                    # Không cần cọc
    PERCENT_30 = "percent_30"        # Cọc 30%
    PERCENT_100 = "percent_100"      # Cọc 100%

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_code = Column(String(50), unique=True, index=True, nullable=False)
    
    # Thông tin khách hàng
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)  # nullable=True cho khách vãng lai
    customer_name = Column(String(255), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    customer_email = Column(String(255))
    customer_address = Column(Text, nullable=False)
    shipping_address = Column(Text, nullable=True)  # legacy DB column; copy from customer_address when creating
    customer_note = Column(Text)
    
    # Thông tin đơn hàng
    subtotal = Column(Numeric(12, 2), default=0)
    shipping_fee = Column(Numeric(12, 2), default=0)
    discount_amount = Column(Numeric(12, 2), default=0)
    total_amount = Column(Numeric(12, 2), default=0)
    
    # Thông tin đặt cọc (Enum dùng value trong DB: 'percent_30', 'waiting_deposit', ...)
    _enum_values = lambda x: [e.value for e in x]
    requires_deposit = Column(Boolean, default=False)
    deposit_type = Column(Enum(DepositType, values_callable=_enum_values), default=DepositType.NONE)
    deposit_percentage = Column(Integer, default=0)
    deposit_amount = Column(Numeric(12, 2), default=0)
    deposit_paid = Column(Numeric(12, 2), default=0)
    remaining_amount = Column(Numeric(12, 2), default=0)

    # Trạng thái
    status = Column(Enum(OrderStatus, values_callable=_enum_values), default=OrderStatus.PENDING)
    payment_method = Column(Enum(PaymentMethod, values_callable=_enum_values))
    payment_status = Column(Enum(PaymentStatus, values_callable=_enum_values), default=PaymentStatus.PENDING)
    
    # Thông tin vận chuyển
    shipping_method = Column(String(100))
    shipping_provider = Column(String(100))
    tracking_number = Column(String(100))
    estimated_delivery = Column(DateTime(timezone=True))
    actual_delivery = Column(DateTime(timezone=True))
    
    # Thông tin quản trị
    admin_notes = Column(Text)
    cancelled_reason = Column(Text)
    processed_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    # Nhân viên chốt đơn đã liên hệ tư vấn khách
    staff_consultation_contacted = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    deposit_paid_at = Column(DateTime(timezone=True))
    confirmed_at = Column(DateTime(timezone=True))
    shipped_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== RELATIONSHIPS ==========
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    admin_manager = relationship("AdminUser", back_populates="orders_managed")
    # ===================================
    
    def __repr__(self):
        return f"<Order {self.order_code}>"

class OrderItem(Base):
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=False)
    product_name = Column(String(500), nullable=False)
    product_image = Column(String(500))
    
    # Thông tin sản phẩm tại thời điểm đặt hàng
    unit_price = Column(Numeric(12, 2), nullable=False)
    price = Column(Numeric(12, 2), nullable=True)  # legacy DB column; copy from unit_price
    quantity = Column(Integer, nullable=False, default=1)
    total_price = Column(Numeric(12, 2), nullable=False)
    
    # Thông tin variant
    selected_size = Column(String(50))
    selected_color = Column(String(50))
    selected_color_name = Column(String(100))
    
    # Đặt cọc cho sản phẩm
    requires_deposit = Column(Boolean, default=False)
    deposit_amount = Column(Numeric(12, 2), default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # ========== RELATIONSHIPS ==========
    order = relationship("Order", back_populates="items")
    product = relationship("Product", lazy="joined")
    # ===================================

    @property
    def product_slug(self):
        return self.product.slug if self.product else None

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    payment_code = Column(String(50), unique=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    
    # Thông tin thanh toán (Enum dùng value trong DB)
    _enum_values = lambda x: [e.value for e in x]
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(Enum(PaymentMethod, values_callable=_enum_values), nullable=False)
    payment_type = Column(String(50))
    payment_status = Column(Enum(PaymentStatus, values_callable=_enum_values), default=PaymentStatus.PENDING)
    
    # Thông tin chuyển khoản
    bank_name = Column(String(100))
    account_number = Column(String(50))
    account_name = Column(String(255))
    # Nội dung CK khớp QR SePay (pending → webhook đối chiếu trực tiếp, không suy đoán từ SMS)
    transfer_content = Column(Text, nullable=True)
    transaction_code = Column(String(100))
    transfer_date = Column(DateTime(timezone=True))
    
    # Xác nhận của admin
    confirmed_by = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True))
    confirmation_note = Column(Text)
    
    # Metadata
    payment_gateway_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== RELATIONSHIPS ==========
    order = relationship("Order", back_populates="payments")
    admin_confirmer = relationship("AdminUser")
    # ===================================