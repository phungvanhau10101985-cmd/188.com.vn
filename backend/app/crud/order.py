# backend/app/crud/order.py - COMPLETE ORDER CRUD WITH DEPOSIT
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, func, desc
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import logging

from app.core.config import settings
from app.models.order import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentStatus,
    PaymentMethod,
    DepositType,
    OrderStatusOverride,
)
from app.models.product import Product
from app.schemas.order import OrderCreate, OrderUpdate
from app.services import affiliate_wallet as affiliate_svc
from app.services import order_shipment_timeline as shipment_svc
from app.services.fulfillment_transition_contract import (
    SOURCE_ROUTINE_TRANSITIONS,
    transition_is_allowed_for_tenant,
)

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
    fulfillment_source: str = "vietnam",
    checkout_group_id: Optional[str] = None,
    split_index: int = 1,
    stock_hold_expires_at: Optional[datetime] = None,
    meta_ads_context: Optional[Dict] = None,
    commit: bool = True,
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
            fulfillment_source=fulfillment_source,
            checkout_group_id=checkout_group_id,
            split_index=split_index,
            stock_hold_expires_at=stock_hold_expires_at,
            meta_ads_context=meta_ads_context,
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
                deposit_amount=item_data['deposit_amount'],
                fulfillment_source=item_data.get('fulfillment_source', fulfillment_source),
                source_platform=item_data.get('source_platform'),
                source_url=item_data.get('source_url'),
                product_sku_snapshot=item_data.get('product_sku_snapshot'),
                is_warehouse_item=bool(item_data.get('is_warehouse_item', False)),
            )
            db.add(order_item)
        
        if commit:
            db.commit()
            db.refresh(order)
        else:
            db.flush()
        
        logger.info(f"Created order {order_code} with deposit: {requires_deposit}")
        return order
        
    except Exception as e:
        if commit:
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
    deposit_base = max(Decimal("0"), total - Decimal(str(order.shipping_fee or 0)))
    if deposit_type == DepositType.PERCENT_100.value:
        order.deposit_percentage = 100
        order.deposit_amount = deposit_base
        order.remaining_amount = total - deposit_base
    else:
        order.deposit_percentage = 30
        order.deposit_amount = (deposit_base * Decimal('0.3')).quantize(Decimal('0.01'))
        order.remaining_amount = (total - order.deposit_amount).quantize(Decimal('0.01'))
    order.deposit_type = DepositType(deposit_type)
    order.updated_at = datetime.now()
    db.commit()
    db.refresh(order)
    return order

def get_order_by_code(db: Session, order_code: str) -> Optional[Order]:
    """Get order by order code (DHxxx — không phân biệt hoa thường)."""
    code = (order_code or "").strip()
    if not code:
        return None
    return db.query(Order).filter(Order.order_code.ilike(code)).first()

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

def _admin_orders_filtered_query(
    db: Session,
    *,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    requires_deposit: Optional[bool] = None,
    fulfillment_source: Optional[str] = None,
    deposit_hold_overdue: Optional[bool] = None,
    fulfillment_needs_review: Optional[bool] = None,
    preset: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    q: Optional[str] = None,
):
    """Query đơn admin sau bộ lọc (chưa order/limit)."""
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
    if fulfillment_source:
        query = query.filter(Order.fulfillment_source == fulfillment_source)
    if deposit_hold_overdue is not None:
        query = query.filter(Order.deposit_hold_overdue == deposit_hold_overdue)
    if fulfillment_needs_review is not None:
        query = query.filter(Order.fulfillment_needs_review == fulfillment_needs_review)
    if preset == "china_no_deposit":
        query = query.filter(
            Order.fulfillment_source == "china",
            Order.requires_deposit.is_(False),
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.PROCESSING.value]),
            Order.shipped_at.is_(None),
        )

    if date_from:
        query = query.filter(Order.created_at >= date_from)

    if date_to:
        query = query.filter(Order.created_at <= date_to)

    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.filter(
            or_(
                Order.order_code.ilike(like),
                Order.customer_name.ilike(like),
                Order.customer_phone.ilike(like),
            )
        )

    return query


def get_orders_admin(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    requires_deposit: Optional[bool] = None,
    fulfillment_source: Optional[str] = None,
    deposit_hold_overdue: Optional[bool] = None,
    fulfillment_needs_review: Optional[bool] = None,
    preset: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    q: Optional[str] = None,
) -> List[Order]:
    """Admin: Get all orders with filters. status có thể là một giá trị hoặc nhiều giá trị cách nhau bởi dấu phẩy."""
    query = _admin_orders_filtered_query(
        db,
        status=status,
        payment_status=payment_status,
        requires_deposit=requires_deposit,
        fulfillment_source=fulfillment_source,
        deposit_hold_overdue=deposit_hold_overdue,
        fulfillment_needs_review=fulfillment_needs_review,
        preset=preset,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    return query.order_by(desc(Order.created_at)).offset(skip).limit(limit).all()


def get_orders_admin_paginated(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    requires_deposit: Optional[bool] = None,
    fulfillment_source: Optional[str] = None,
    deposit_hold_overdue: Optional[bool] = None,
    fulfillment_needs_review: Optional[bool] = None,
    preset: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    q: Optional[str] = None,
) -> tuple[List[Order], int]:
    """Admin: danh sách đơn + tổng sau lọc (phân trang)."""
    query = _admin_orders_filtered_query(
        db,
        status=status,
        payment_status=payment_status,
        requires_deposit=requires_deposit,
        fulfillment_source=fulfillment_source,
        deposit_hold_overdue=deposit_hold_overdue,
        fulfillment_needs_review=fulfillment_needs_review,
        preset=preset,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )
    filtered_total = query.count()
    items = query.order_by(desc(Order.created_at)).offset(skip).limit(limit).all()
    return items, filtered_total

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
    
    update_data = order_update.model_dump(exclude_unset=True)
    old_status = getattr(order.status, "value", order.status)
    
    override_reason = str(update_data.pop("override_reason", "") or "").strip()
    status_was_overridden = False

    # Update status timestamps
    if 'status' in update_data:
        new_status = update_data['status']
        new_status_val = getattr(new_status, "value", new_status)
        if new_status_val != old_status:
            terminal_targets = {
                OrderStatus.CANCELLED.value,
                OrderStatus.DELIVERED.value,
                OrderStatus.COMPLETED.value,
                OrderStatus.RETURNED.value,
            }
            normally_allowed = transition_is_allowed_for_tenant(
                settings.SERVER_NAME,
                old_status,
                new_status_val,
            )
            source = (order.fulfillment_source or "vietnam").strip().lower()
            is_source_routine = new_status_val in SOURCE_ROUTINE_TRANSITIONS.get(
                source, {}
            ).get(old_status, set())
            if new_status_val not in terminal_targets:
                if not override_reason:
                    route_hint = (
                        "dùng nút soạn/đóng gói hoặc nhập EMS"
                        if source == "vietnam"
                        else "dùng timeline Trung Quốc/EMS"
                    )
                    if not is_source_routine:
                        route_hint = f"chuyển trạng thái này không thuộc luồng {source}"
                    raise ValueError(
                        f"Không đổi trạng thái vận hành trực tiếp; {route_hint}. "
                        "Nếu thật sự cần ghi đè, phải nhập override_reason."
                    )
                status_was_overridden = True
            elif not normally_allowed and not override_reason:
                raise ValueError(
                    f"Không thể chuyển trạng thái từ {old_status or 'trống'} sang {new_status_val}."
                )
            elif not normally_allowed:
                status_was_overridden = True
        now = datetime.now()
        
        if new_status_val == OrderStatus.CONFIRMED.value:
            order.confirmed_at = now
        elif new_status_val == OrderStatus.SHIPPING.value:
            order.shipped_at = now
        elif new_status_val == OrderStatus.DELIVERED.value:
            pass
        elif new_status_val == OrderStatus.COMPLETED.value:
            order.completed_at = now
        elif new_status_val == OrderStatus.CANCELLED.value:
            order.cancelled_at = now
        elif new_status_val == OrderStatus.RETURNED.value:
            order.returned_at = now
    
    # Update fields
    for field, value in update_data.items():
        if hasattr(order, field):
            setattr(order, field, value)
    if status_was_overridden:
        audit_note = (
            f"[Ghi đè trạng thái] {old_status} → {new_status_val}; lý do: {override_reason}"
        )
        order.admin_notes = "\n".join(
            part for part in [order.admin_notes, audit_note] if part
        )
        db.add(
            OrderStatusOverride(
                order_id=order.id,
                from_status=old_status or "",
                to_status=str(new_status_val),
                admin_id=admin_id,
                reason=override_reason,
            )
        )
    
    order.processed_by = admin_id
    order.updated_at = datetime.now()

    commission_confirmed = False
    if 'status' in update_data:
        new_status_val = getattr(update_data['status'], "value", update_data['status'])
        from app.services.warehouse_stock import sync_warehouse_stock_on_status_change

        if new_status_val == OrderStatus.DELIVERED.value:
            from app.services.order_delivery import mark_order_delivered

            mark_order_delivered(
                db,
                order,
                source="admin",
                admin_id=admin_id,
                previous_status=old_status,
            )
            commission_confirmed = bool(
                getattr(order, "_delivery_commission_confirmed", False)
            )
        else:
            sync_warehouse_stock_on_status_change(db, order, old_status, new_status_val)
            commission_confirmed = affiliate_svc.handle_order_status_change(
                db, order, old_status, new_status_val
            )
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
    from app.services.warehouse_stock import sync_warehouse_stock_on_status_change

    sync_warehouse_stock_on_status_change(db, order, old_status, OrderStatus.CANCELLED.value)
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
    from app.services.order_delivery import mark_order_delivered

    mark_order_delivered(db, order, source="customer_confirm")
    commission_confirmed = bool(
        getattr(order, "_delivery_commission_confirmed", False)
    )
    db.commit()
    db.refresh(order)
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


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw or "")


def _money_key(value: Any) -> str:
    try:
        return format(Decimal(value or 0).quantize(Decimal("0.01")), "f")
    except Exception:
        return "0.00"


def _phone_key(phone: str | None) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits


def _items_signature(items: Any) -> tuple:
    parts = []
    for item in items or []:
        unit = item.unit_price if item.unit_price is not None else item.price
        parts.append(
            (
                int(item.product_id or 0),
                int(item.quantity or 0),
                (item.selected_size or "").strip().lower(),
                (item.selected_color or "").strip().lower(),
                _money_key(unit),
            )
        )
    parts.sort()
    return tuple(parts)


def revenue_duplicate_key(order: Order, items: Any = None) -> tuple:
    """Đơn trùng: cùng SĐT, cùng tổng tiền, cùng dòng hàng (SP, SL, biến thể, giá)."""
    return (
        _phone_key(order.customer_phone),
        _money_key(order.total_amount),
        _items_signature(items if items is not None else getattr(order, "items", None)),
    )


def order_counts_as_deposited(order: Order) -> bool:
    if _enum_value(order.status) == OrderStatus.CANCELLED.value:
        return False
    if _enum_value(order.payment_status) == PaymentStatus.REFUNDED.value:
        return False
    if Decimal(order.deposit_paid or 0) > 0:
        return True
    if order.deposit_paid_at is not None:
        return True
    if _enum_value(order.payment_status) == PaymentStatus.DEPOSIT_PAID.value:
        return True
    return _enum_value(order.status) == OrderStatus.DEPOSIT_PAID.value


def _aware_dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def pick_revenue_representative(orders: List[Order]) -> Order:
    """
    Một nhóm đơn trùng chỉ giữ 1 đơn.
    Có đơn đã cọc thì giữ đơn đã cọc; không có thì giữ 1 đơn chưa cọc.
    """
    deposited = [order for order in orders if order_counts_as_deposited(order)]
    if deposited:
        pool = deposited
    else:
        live = [
            order
            for order in orders
            if _enum_value(order.payment_status) != PaymentStatus.REFUNDED.value
        ]
        pool = live or list(orders)

    def rank(order: Order) -> tuple:
        return (
            _aware_dt(order.deposit_paid_at),
            _aware_dt(order.created_at),
            int(order.id or 0),
        )

    return max(pool, key=rank)


def dedupe_orders_for_revenue(
    orders: List[Order],
    items_by_order: Optional[Dict[int, list]] = None,
) -> List[Order]:
    grouped: Dict[tuple, List[Order]] = {}
    lookup = items_by_order or {}
    for order in orders:
        key = revenue_duplicate_key(order, lookup.get(order.id, []))
        grouped.setdefault(key, []).append(order)
    return [pick_revenue_representative(group) for group in grouped.values()]


def _collected_deposit(order: Order) -> Decimal:
    paid = Decimal(order.deposit_paid or 0)
    if paid != 0:
        return paid
    return Decimal(order.deposit_amount or 0)


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

    cancelled_orders = query.filter(Order.status == OrderStatus.CANCELLED.value).count()
    # Doanh thu và tổng đơn không gồm đơn đã hủy.
    # Đơn trùng (cùng SĐT + cùng hàng + cùng tổng tiền) chỉ tính 1 lần;
    # trong nhóm có đơn đã cọc thì chỉ tính đơn đã cọc.
    active_orders = query.filter(Order.status != OrderStatus.CANCELLED.value).all()
    items_by_order: Dict[int, list] = {}
    order_ids = [order.id for order in active_orders if order.id is not None]
    if order_ids:
        # Chỉ cột dòng hàng — không load Product (relationship joined kéo bảng products).
        item_rows = (
            db.query(
                OrderItem.order_id,
                OrderItem.product_id,
                OrderItem.quantity,
                OrderItem.selected_size,
                OrderItem.selected_color,
                OrderItem.unit_price,
                OrderItem.price,
            )
            .filter(OrderItem.order_id.in_(order_ids))
            .all()
        )
        for row in item_rows:
            items_by_order.setdefault(row.order_id, []).append(row)
    representatives = dedupe_orders_for_revenue(active_orders, items_by_order)
    total_orders = len(representatives)
    total_revenue = sum(
        (Decimal(order.total_amount or 0) for order in representatives),
        Decimal("0"),
    )
    orders_including_cancelled = total_orders + cancelled_orders

    status_counts: Dict[str, int] = {f"{status.value}_orders": 0 for status in OrderStatus}
    status_counts["cancelled_orders"] = cancelled_orders
    for order in representatives:
        key = f"{_enum_value(order.status)}_orders"
        if key in status_counts and key != "cancelled_orders":
            status_counts[key] += 1

    deposited_orders_list = [order for order in representatives if order_counts_as_deposited(order)]
    deposited_orders = len(deposited_orders_list)
    deposited_revenue = sum(
        (Decimal(order.total_amount or 0) for order in deposited_orders_list),
        Decimal("0"),
    )
    deposited_amount = sum(
        (_collected_deposit(order) for order in deposited_orders_list),
        Decimal("0"),
    )

    return {
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "orders_including_cancelled": orders_including_cancelled,
        "deposited_orders": deposited_orders,
        "deposited_revenue": deposited_revenue,
        "deposited_amount": deposited_amount,
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