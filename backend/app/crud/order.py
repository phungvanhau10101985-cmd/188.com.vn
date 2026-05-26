# backend/app/crud/order.py - COMPLETE ORDER CRUD WITH DEPOSIT
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import and_, or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus, PaymentMethod, DepositType
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderUpdate
from app.services import affiliate_wallet as affiliate_svc
from app.services import order_shipment_timeline as shipment_svc

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
    admin_notes: Optional[str] = None,
    referrer_user_id: Optional[int] = None,
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
            referrer_user_id=referrer_user_id,
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


def get_order_with_items(db: Session, order_id: int) -> Optional[Order]:
    """GET chi tiết đơn (khách/API) — eager load items để response luôn có dòng hàng."""
    return (
        db.query(Order)
        .options(selectinload(Order.items))
        .filter(Order.id == order_id)
        .first()
    )


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
    old_status = getattr(order.status, "value", order.status)
    
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
        elif new_status == OrderStatus.RETURNED.value:
            order.returned_at = now
    
    # Update fields
    for field, value in update_data.items():
        if hasattr(order, field):
            setattr(order, field, value)
    
    order.processed_by = admin_id
    order.updated_at = datetime.now()

    commission_confirmed = False
    if 'status' in update_data:
        commission_confirmed = affiliate_svc.handle_order_status_change(db, order, old_status, update_data['status'])
        if update_data['status'] == OrderStatus.DELIVERED.value:
            shipment_svc.mark_delivered_on_timeline(db, order, admin_id=admin_id)
            if order.user_id:
                try:
                    from app.services import promotion_grants as grant_svc

                    grant_svc.process_first_delivered_grants(db, order.user_id)
                except Exception:
                    pass
    if 'payment_status' in update_data:
        affiliate_svc.handle_order_payment_status_change(db, order, update_data['payment_status'])
    
    db.commit()
    db.refresh(order)
    if commission_confirmed:
        affiliate_svc.notify_referrer_commission_confirmed_task(order.id)
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
    status_val = getattr(order.status, "value", order.status)
    
    # Check if order can be cancelled
    if status_val in (
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
        OrderStatus.RETURNED.value,
    ):
        return None
    
    order.status = OrderStatus.CANCELLED.value
    order.cancelled_reason = reason
    order.cancelled_at = datetime.now()
    order.updated_at = datetime.now()

    old_status = status_val
    affiliate_svc.handle_order_status_change(db, order, old_status, OrderStatus.CANCELLED.value)
    
    db.commit()
    db.refresh(order)
    return order

def confirm_received(
    db: Session,
    order_id: int,
    user_id: int
) -> Optional[Order]:
    """Khách hàng xác nhận đã nhận hàng (shipping + bước awaiting_confirm active -> delivered)"""
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user_id
    ).first()
    if not order:
        return None
    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatus.SHIPPING.value:
        return None
    if not shipment_svc.can_customer_confirm_received(db, order):
        return None
    old_status = status_val
    order.status = OrderStatus.DELIVERED.value
    order.delivered_at = datetime.now()
    order.updated_at = datetime.now()
    commission_confirmed = affiliate_svc.handle_order_status_change(db, order, old_status, OrderStatus.DELIVERED.value)
    shipment_svc.mark_delivered_on_timeline(db, order)
    db.commit()
    db.refresh(order)
    if order.user_id:
        try:
            from app.services import promotion_grants as grant_svc

            grant_svc.process_first_delivered_grants(db, order.user_id)
        except Exception:
            pass
    if commission_confirmed:
        affiliate_svc.notify_referrer_commission_confirmed_task(order.id)
    return order

_VN_TZ = timezone(timedelta(hours=7))
_ORDER_STATS_PRESETS = frozenset(
    {"today", "this_week", "last_week", "this_month", "last_month"}
)


def _vn_today() -> date:
    return datetime.now(_VN_TZ).date()


def _parse_iso_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Ngày không hợp lệ: {value}") from exc


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _datetime_start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time())


def _datetime_end(day: date) -> datetime:
    return datetime.combine(day, datetime.max.time())


def resolve_order_stats_range(
    *,
    period: str = "today",
    preset: str | None = None,
    on_date: str | None = None,
    year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[datetime | None, datetime | None, str, str | None, str | None]:
    """
    Trả về (start_dt, end_dt, period_label, iso_from, iso_to).
    start/end None = không lọc theo ngày (period=all).
    """
    preset_key = (preset or "").strip().lower()
    if preset_key and preset_key not in _ORDER_STATS_PRESETS:
        raise ValueError(
            "preset phải là today, this_week, last_week, this_month hoặc last_month."
        )

    if on_date and not date_from and not date_to:
        day = _parse_iso_date(on_date)
        assert day is not None
        return (
            _datetime_start(day),
            _datetime_end(day),
            day.strftime("%d/%m/%Y"),
            day.isoformat(),
            day.isoformat(),
        )

    if preset_key == "today":
        today = _vn_today()
        return (
            _datetime_start(today),
            _datetime_end(today),
            f"Hôm nay ({today.strftime('%d/%m/%Y')})",
            today.isoformat(),
            today.isoformat(),
        )

    if preset_key == "this_week":
        today = _vn_today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label = f"Tuần này ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if preset_key == "last_week":
        today = _vn_today()
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        end = start + timedelta(days=6)
        label = f"Tuần trước ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if preset_key == "this_month":
        today = _vn_today()
        start, end = _month_bounds(today.year, today.month)
        label = f"Tháng này ({today.month:02d}/{today.year})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if preset_key == "last_month":
        today = _vn_today()
        prev_year = today.year - 1 if today.month == 1 else today.year
        prev_month = 12 if today.month == 1 else today.month - 1
        start, end = _month_bounds(prev_year, prev_month)
        label = f"Tháng trước ({prev_month:02d}/{prev_year})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if year is not None:
        y = int(year)
        if y < 1970 or y > 2100:
            raise ValueError("Năm không hợp lệ.")
        start = date(y, 1, 1)
        end = date(y, 12, 31)
        return _datetime_start(start), _datetime_end(end), str(y), start.isoformat(), end.isoformat()

    parsed_from = _parse_iso_date(date_from) if date_from else None
    parsed_to = _parse_iso_date(date_to) if date_to else None
    if parsed_from or parsed_to:
        start = parsed_from or parsed_to
        end = parsed_to or parsed_from
        assert start is not None and end is not None
        if start > end:
            start, end = end, start
        if start == end:
            label = start.strftime("%d/%m/%Y")
        else:
            label = f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')}"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    legacy = (period or "today").strip().lower()
    if legacy == "week":
        today = _vn_today()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        label = f"Tuần này ({start.strftime('%d/%m')} – {end.strftime('%d/%m/%Y')})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if legacy == "month":
        today = _vn_today()
        start, end = _month_bounds(today.year, today.month)
        label = f"Tháng này ({today.month:02d}/{today.year})"
        return _datetime_start(start), _datetime_end(end), label, start.isoformat(), end.isoformat()

    if legacy == "year":
        today = _vn_today()
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)
        return (
            _datetime_start(start),
            _datetime_end(end),
            f"Năm {today.year}",
            start.isoformat(),
            end.isoformat(),
        )

    if legacy == "all":
        return None, None, "Tất cả", None, None

    today = _vn_today()
    return (
        _datetime_start(today),
        _datetime_end(today),
        f"Hôm nay ({today.strftime('%d/%m/%Y')})",
        today.isoformat(),
        today.isoformat(),
    )


def get_order_stats(
    db: Session,
    period: str = "today",
    *,
    preset: str | None = None,
    on_date: str | None = None,
    year: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Dict[str, Any]:
    """Thống kê đơn hàng + doanh thu theo khoảng thời gian."""
    start_dt, end_dt, period_label, iso_from, iso_to = resolve_order_stats_range(
        period=period,
        preset=preset,
        on_date=on_date,
        year=year,
        date_from=date_from,
        date_to=date_to,
    )

    query = db.query(Order)

    if start_dt is not None and end_dt is not None:
        query = query.filter(
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )

    total_orders = query.count()
    total_revenue_result = query.with_entities(func.sum(Order.total_amount)).scalar()
    total_revenue = total_revenue_result if total_revenue_result else Decimal("0")

    status_counts: Dict[str, int] = {}
    for status in OrderStatus:
        count = query.filter(Order.status == status.value).count()
        status_counts[f"{status.value}_orders"] = count

    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "period_label": period_label,
        "date_from": iso_from,
        "date_to": iso_to,
        **status_counts,
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
        old_status = OrderStatus.DELIVERED.value
        order.status = OrderStatus.COMPLETED.value
        order.completed_at = datetime.now()
        commission_confirmed = affiliate_svc.handle_order_status_change(db, order, old_status, OrderStatus.COMPLETED.value)
        db.commit()
        if commission_confirmed:
            affiliate_svc.notify_referrer_commission_confirmed_task(order.id)


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