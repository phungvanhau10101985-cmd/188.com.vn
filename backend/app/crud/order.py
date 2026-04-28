# backend/app/crud/order.py - COMPLETE ORDER CRUD WITH DEPOSIT
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus, PaymentMethod, DepositType
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderUpdate

logger = logging.getLogger(__name__)

def generate_order_code(db: Session) -> str:
    """Mã đơn hàng ngắn: DH001, DH002, ... (2 chữ + 3 số)"""
    max_id = db.query(func.coalesce(func.max(Order.id), 0)).scalar() or 0
    return f"DH{max_id + 1:03d}"

def calculate_deposit(product: Product, deposit_type: str) -> Decimal:
    """Calculate deposit amount for a product"""
    if not product.deposit_require:
        return Decimal('0')
    
    if deposit_type == DepositType.PERCENT_30.value:
        return product.price * Decimal('0.3')
    elif deposit_type == DepositType.PERCENT_100.value:
        return product.price
    else:
        return Decimal('0')

def create_order_with_deposit(
    db: Session,
    user_id: Optional[int],
    customer_name: str,
    customer_phone: str,
    customer_email: Optional[str],
    customer_address: str,
    customer_note: Optional[str],
    payment_method: str,
    shipping_method: Optional[str],
    subtotal: Decimal,
    shipping_fee: Decimal,
    total_amount: Decimal,
    requires_deposit: bool,
    deposit_type: Optional[str],
    deposit_percentage: int,
    deposit_amount: Decimal,
    remaining_amount: Decimal,
    items: List[Dict],
    discount_amount: Decimal = Decimal('0'),
    admin_notes: Optional[str] = None
) -> Order:
    """Create new order with deposit calculation"""
    try:
        # Generate order code (DH001, DH002, ...)
        order_code = generate_order_code(db)
        
        # Create order
        # Convert string values to enums for SQLAlchemy
        deposit_type_enum = DepositType(deposit_type) if deposit_type else None
        status_enum = OrderStatus.WAITING_DEPOSIT if requires_deposit else OrderStatus.CONFIRMED
        payment_status_enum = PaymentStatus.PENDING
        payment_method_enum = PaymentMethod(payment_method) if payment_method else None

        order = Order(
            order_code=order_code,
            user_id=user_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            customer_address=customer_address,
            shipping_address=customer_address,  # legacy column; keep in sync
            customer_note=customer_note,
            subtotal=subtotal,
            shipping_fee=shipping_fee,
            total_amount=total_amount,
            discount_amount=discount_amount,
            admin_notes=admin_notes,
            requires_deposit=requires_deposit,
            deposit_type=deposit_type_enum,
            deposit_percentage=deposit_percentage,
            deposit_amount=deposit_amount,
            remaining_amount=remaining_amount,
            payment_method=payment_method_enum,
            shipping_method=shipping_method,
            status=status_enum,
            payment_status=payment_status_enum,
        )
        db.add(order)
        db.flush()  # Get order ID
        
        # Create order items
        for item_data in items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data['product_id'],
                product_name=item_data['product_name'],
                product_image=item_data['product_image'],
                unit_price=item_data['unit_price'],
                price=item_data['unit_price'],  # legacy column; keep in sync
                quantity=item_data['quantity'],
                total_price=item_data['total_price'],
                selected_size=item_data.get('selected_size'),
                selected_color=item_data.get('selected_color'),
                selected_color_name=item_data.get('selected_color_name'),
                requires_deposit=item_data['requires_deposit'],
                deposit_amount=item_data['deposit_amount']
            )
            db.add(order_item)
        
        db.commit()
        db.refresh(order)
        
        logger.info(f"Created order {order_code} with deposit: {requires_deposit}")
        return order
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating order: {str(e)}")
        raise

def get_order(db: Session, order_id: int) -> Optional[Order]:
    """Get order by ID"""
    return db.query(Order).filter(Order.id == order_id).first()

def update_order_deposit_type(
    db: Session,
    order_id: int,
    user_id: int,
    deposit_type: str,
) -> Optional[Order]:
    """Khách hàng đổi mức cọc (30% hoặc 100%) khi đơn đang chờ đặt cọc."""
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        return None
    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatus.WAITING_DEPOSIT.value:
        return None
    if deposit_type not in (DepositType.PERCENT_30.value, DepositType.PERCENT_100.value):
        return None
    total = Decimal(str(order.total_amount))
    if deposit_type == DepositType.PERCENT_100.value:
        order.deposit_percentage = 100
        order.deposit_amount = total
        order.remaining_amount = Decimal('0')
    else:
        order.deposit_percentage = 30
        order.deposit_amount = (total * Decimal('0.3')).quantize(Decimal('0.01'))
        order.remaining_amount = (total - order.deposit_amount).quantize(Decimal('0.01'))
    order.deposit_type = DepositType(deposit_type)
    order.updated_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order

def get_order_by_code(db: Session, order_code: str) -> Optional[Order]:
    """Get order by order code"""
    return db.query(Order).filter(Order.order_code == order_code).first()

def get_user_orders(
    db: Session, 
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None
) -> List[Order]:
    """Get orders for a user"""
    query = db.query(Order).filter(Order.user_id == user_id)
    
    if status:
        query = query.filter(Order.status == status)
    
    query = query.order_by(desc(Order.created_at))
    return query.offset(skip).limit(limit).all()

def get_orders_admin(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    requires_deposit: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
) -> List[Order]:
    """Admin: Get all orders with filters. status có thể là một giá trị hoặc nhiều giá trị cách nhau bởi dấu phẩy."""
    query = db.query(Order)
    
    if status:
        status_list = [s.strip() for s in status.split(",") if s.strip()]
        if len(status_list) == 1:
            query = query.filter(Order.status == status_list[0])
        elif status_list:
            query = query.filter(Order.status.in_(status_list))
    
    if payment_status:
        query = query.filter(Order.payment_status == payment_status)
    
    if requires_deposit is not None:
        query = query.filter(Order.requires_deposit == requires_deposit)
    
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    
    if date_to:
        query = query.filter(Order.created_at <= date_to)
    
    query = query.order_by(desc(Order.created_at))
    return query.offset(skip).limit(limit).all()

def admin_update_order(
    db: Session,
    order_id: int,
    order_update: OrderUpdate,
    admin_id: int
) -> Optional[Order]:
    """Admin: Update order"""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return None
    
    update_data = order_update.dict(exclude_unset=True)
    
    # Update status timestamps
    if 'status' in update_data:
        new_status = update_data['status']
        now = datetime.now()
        
        if new_status == OrderStatus.CONFIRMED.value:
            order.confirmed_at = now
        elif new_status == OrderStatus.SHIPPING.value:
            order.shipped_at = now
        elif new_status == OrderStatus.DELIVERED.value:
            order.delivered_at = now
        elif new_status == OrderStatus.COMPLETED.value:
            order.completed_at = now
        elif new_status == OrderStatus.CANCELLED.value:
            order.cancelled_at = now
    
    # Update fields
    for field, value in update_data.items():
        if hasattr(order, field):
            setattr(order, field, value)
    
    order.processed_by = admin_id
    order.updated_at = datetime.now()
    
    db.commit()
    db.refresh(order)
    return order

def cancel_order(
    db: Session,
    order_id: int,
    user_id: int,
    reason: str
) -> Optional[Order]:
    """Cancel order (user)"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user_id
    ).first()
    
    if not order:
        return None
    
    # Check if order can be cancelled
    if order.status in [OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value]:
        return None
    
    order.status = OrderStatus.CANCELLED.value
    order.cancelled_reason = reason
    order.cancelled_at = datetime.now()
    order.updated_at = datetime.now()
    
    db.commit()
    db.refresh(order)
    return order

def confirm_received(
    db: Session,
    order_id: int,
    user_id: int
) -> Optional[Order]:
    """Khách hàng xác nhận đã nhận hàng (deposit_paid/confirmed/processing/shipping -> delivered)"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user_id
    ).first()
    if not order:
        return None
    status_val = getattr(order.status, "value", order.status)
    # Cho phép xác nhận từ các trạng thái trong tab "Chờ nhận hàng"
    allowed_statuses = [
        OrderStatus.DEPOSIT_PAID.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPING.value
    ]
    if status_val not in allowed_statuses:
        return None
    order.status = OrderStatus.DELIVERED.value
    order.delivered_at = datetime.now()
    order.updated_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order

def get_order_stats(db: Session, period: str = "today") -> Dict[str, Any]:
    """Get order statistics"""
    today = datetime.now().date()
    
    if period == "today":
        start_date = datetime.combine(today, datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif period == "month":
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    elif period == "year":
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)
    else:  # all
        start_date = None
        end_date = None
    
    query = db.query(Order)
    
    if start_date and end_date:
        query = query.filter(
            Order.created_at >= start_date,
            Order.created_at <= end_date
        )
    
    # Total orders and revenue
    total_orders = query.count()
    total_revenue_result = query.with_entities(func.sum(Order.total_amount)).scalar()
    total_revenue = total_revenue_result if total_revenue_result else Decimal('0')
    
    # Count by status
    status_counts = {}
    for status in OrderStatus:
        count = query.filter(Order.status == status.value).count()
        status_counts[f"{status.value}_orders"] = count
    
    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        **status_counts
    }


def has_user_purchased_product(db: Session, user_id: int, product_id: int) -> bool:
    """Kiểm tra user đã mua sản phẩm (có đơn hàng chứa product_id, trạng thái không hủy)."""
    from app.models.order import OrderItem
    row = (
        db.query(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.user_id == user_id,
            OrderItem.product_id == product_id,
            Order.status != OrderStatus.CANCELLED.value,
        )
        .limit(1)
        .first()
    )
    return row is not None


def mark_order_completed_if_reviewed(db: Session, user_id: int, product_id: int) -> None:
    """Khi khách đánh giá 1 sản phẩm trong đơn → cập nhật đơn delivered sang completed."""
    from app.models.order import OrderItem
    order = (
        db.query(Order)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .filter(
            Order.user_id == user_id,
            OrderItem.product_id == product_id,
            Order.status == OrderStatus.DELIVERED.value,
        )
        .first()
    )
    if order:
        order.status = OrderStatus.COMPLETED.value
        order.completed_at = datetime.now()
        db.commit()


def has_user_purchased_product_for_review(db: Session, user_id: int, product_id: int) -> bool:
    """Chỉ cho phép đánh giá khi đã nhận hàng (delivered hoặc completed)."""
    from app.models.order import OrderItem
    row = (
        db.query(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.user_id == user_id,
            OrderItem.product_id == product_id,
            Order.status.in_([OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value]),
        )
        .limit(1)
        .first()
    )
    return row is not None