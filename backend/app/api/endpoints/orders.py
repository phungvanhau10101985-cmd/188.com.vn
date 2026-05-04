# backend/app/api/endpoints/orders.py - COMPLETE ORDER API WITH DEPOSIT
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from app.db.session import get_db
from app import crud, models, schemas
from app.crud import loyalty as crud_loyalty
from app.models.order import OrderStatus as OrderStatusEnum, DepositType as DepositTypeEnum, PaymentStatus as PaymentStatusEnum
from app.core.security import get_current_user, get_current_user_optional, require_module_permission
from app.core.config import settings
from app.services.email_service import send_order_email, send_deposit_confirmed_email_task
from app.services import sepay as sepay_svc


def _dec(v) -> Decimal:
    """Chuẩn hóa Numeric/Decimal/str về Decimal (0 nếu rỗng)."""
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


def _admin_expected_deposit_rows(order: models.Order) -> bool:
    """Đơn cần cọc theo cờ Order hoặc theo ít nhất một dòng hàng có requires_deposit (dữ liệu lệch cờ)."""
    if getattr(order, "requires_deposit", False):
        return True
    for row in getattr(order, "items", None) or []:
        if getattr(row, "requires_deposit", False):
            return True
    return False


def resolve_order_deposit_due(order: models.Order) -> Decimal:
    """
    Số tiền cọc cần thu: khớp logic khách hàng FE / admin FE — ưu tiên deposit_amount lưu;
    nếu bằng 0 nhưng đơn thuộc trường hợp cần cọc thì suy từ % / deposit_type / mặc định 30%.
    """
    stored = _dec(getattr(order, "deposit_amount", None))
    if stored > 0:
        return stored.quantize(Decimal("0.01"))

    if not _admin_expected_deposit_rows(order):
        return Decimal("0")

    total = _dec(order.total_amount)
    if total <= 0:
        return Decimal("0")

    dt = getattr(order.deposit_type, "value", order.deposit_type)
    pct = int(getattr(order, "deposit_percentage", None) or 0)

    if dt == DepositTypeEnum.PERCENT_100.value or pct == 100:
        return total.quantize(Decimal("0.01"))
    if dt == DepositTypeEnum.PERCENT_30.value or pct == 30:
        return (total * Decimal("0.3")).quantize(Decimal("0.01"))

    status_val = getattr(order.status, "value", order.status)
    if status_val == OrderStatusEnum.WAITING_DEPOSIT.value:
        return (total * Decimal("0.3")).quantize(Decimal("0.01"))
    return Decimal("0")


router = APIRouter()

# ========== USER ORDER ENDPOINTS ==========
@router.post("", response_model=schemas.OrderResponse, include_in_schema=False)
@router.post("/", response_model=schemas.OrderResponse)
def create_order(
    order_data: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user_optional),
):
    """
    Create new order with deposit calculation.
    Khách chưa đăng nhập: user_id để trống, không áp dụng giảm giá loyalty.
    """
    try:
        # 1. Validate items and calculate deposit
        items = []
        total_amount = Decimal('0')
        requires_deposit = False
        
        for item in order_data.items:
            product = crud.product.get_product(db, item.product_id)
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            
            # Check if product requires deposit
            if product.deposit_require:
                requires_deposit = True
            
            # Calculate item total (product.price is Float in DB → convert to Decimal)
            unit_price = Decimal(str(product.price))
            item_total = unit_price * item.quantity
            total_amount += item_total

            items.append({
                "product_id": product.id,
                "product_name": product.name,
                "product_image": product.main_image,
                "unit_price": unit_price,
                "quantity": item.quantity,
                "total_price": item_total,
                "selected_size": item.selected_size,
                "selected_color": item.selected_color,
                "selected_color_name": item.selected_color_name,
                "requires_deposit": product.deposit_require,
                "deposit_amount": unit_price * Decimal('0.3') if product.deposit_require else Decimal('0')
            })
        
        # --- LOYALTY CALCULATION (chỉ khi đã đăng nhập) ---
        loyalty_discount_amount = Decimal('0')
        loyalty_note = ""

        if current_user is not None:
            total_spent_6_months = crud_loyalty.calculate_user_spend_6_months(db, current_user.id)
            current_tier = crud_loyalty.get_tier_by_spend(db, total_spent_6_months)

            if current_tier and current_tier.discount_percent > 0:
                discount_percent = Decimal(str(current_tier.discount_percent))
                loyalty_discount_amount = (total_amount * discount_percent) / 100
                loyalty_note = f"Giảm giá thành viên {current_tier.name} ({current_tier.discount_percent}%): -{loyalty_discount_amount:,.0f} đ"
            
        # Apply discount
        total_amount_after_discount = total_amount - loyalty_discount_amount

        # 2. Calculate deposit
        deposit_type = order_data.deposit_type
        # SP yêu cầu cọc nhưng client không gửi deposit_type → mặc định 30% (tránh requires_deposit=True với deposit_amount=0)
        if requires_deposit and deposit_type is None:
            deposit_type = schemas.DepositType.PERCENT_30

        deposit_amount = Decimal('0')
        deposit_percentage = 0

        if requires_deposit and deposit_type:
            if deposit_type == schemas.DepositType.PERCENT_30:
                deposit_percentage = 30
                deposit_amount = total_amount_after_discount * Decimal('0.3')
            elif deposit_type == schemas.DepositType.PERCENT_100:
                deposit_percentage = 100
                deposit_amount = total_amount_after_discount
            elif deposit_type == schemas.DepositType.NONE:
                requires_deposit = False
        
        # 3. Calculate shipping fee (simplified)
        shipping_fee = Decimal('30000') if total_amount_after_discount < Decimal('500000') else Decimal('0')
        
        # 4. Create order
        order = crud.order.create_order_with_deposit(
            db=db,
            user_id=current_user.id if current_user else None,
            customer_name=order_data.customer_name,
            customer_phone=order_data.customer_phone,
            customer_email=order_data.customer_email,
            customer_address=order_data.customer_address,
            customer_note=order_data.customer_note,
            payment_method=order_data.payment_method.value,
            shipping_method=order_data.shipping_method,
            subtotal=total_amount,
            discount_amount=loyalty_discount_amount,
            shipping_fee=shipping_fee,
            total_amount=total_amount_after_discount + shipping_fee,
            admin_notes=loyalty_note,
            requires_deposit=requires_deposit,
            deposit_type=deposit_type.value if deposit_type else None,
            deposit_percentage=deposit_percentage,
            deposit_amount=deposit_amount,
            remaining_amount=(total_amount_after_discount + shipping_fee) - deposit_amount,
            items=items
        )
        
        # 5. If deposit required, set status to WAITING_DEPOSIT (use enum, not .value)
        if requires_deposit:
            order.status = OrderStatusEnum.WAITING_DEPOSIT
            db.commit()
            db.refresh(order)
        
        recipient = order.customer_email or (getattr(current_user, "email", None) if current_user else None)
        if recipient:
            background_tasks.add_task(
                send_order_email,
                recipient,
                f"Xác nhận đơn hàng {order.order_code}",
                "Đơn hàng của bạn đã được tạo thành công. Cảm ơn bạn đã mua sắm tại 188.com.vn.",
            )
        return order
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import logging
        logging.getLogger(__name__).exception("Error creating order: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=List[schemas.OrderResponse], include_in_schema=False)
@router.get("/", response_model=List[schemas.OrderResponse])
def read_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    status: Optional[str] = None
):
    """
    Get user's orders
    """
    return crud.order.get_user_orders(
        db, user_id=current_user.id,
        skip=skip, limit=limit, status=status
    )

# ========== PAYMENT/DEPOSIT ENDPOINTS (specific paths before /{order_id}) ==========
@router.patch("/{order_id}/deposit-type", response_model=schemas.OrderResponse)
def update_deposit_type(
    order_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Khách hàng đổi mức cọc (30% hoặc 100%) khi đơn đang chờ đặt cọc.
    Body: { "deposit_type": "percent_30" | "percent_100" }
    """
    deposit_type = body.get("deposit_type")
    if deposit_type not in ("percent_30", "percent_100"):
        raise HTTPException(status_code=400, detail="deposit_type phải là percent_30 hoặc percent_100")
    order = crud.order.update_order_deposit_type(
        db=db,
        order_id=order_id,
        user_id=current_user.id,
        deposit_type=deposit_type,
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or cannot update")
    return order

@router.get("/{order_id}/sepay-deposit-info", response_model=schemas.SepayDepositInfoResponse)
def get_sepay_deposit_info(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Thông tin QR SePay (qr.sepay.vn) + nội dung CK — chỉ khi đơn chờ cọc.
    Cấu hình: SEPAY_QR_BANK_CODE, SEPAY_QR_ACCOUNT_NUMBER trong .env backend.
    """
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatusEnum.WAITING_DEPOSIT.value or not order.requires_deposit:
        raise HTTPException(status_code=400, detail="Đơn không ở trạng thái chờ đặt cọc")

    transfer_content = sepay_svc.build_transfer_content_for_order(order)
    amount = Decimal(str(order.deposit_amount))
    crud.payment.upsert_pending_sepay_deposit_payment(
        db,
        order_id=order.id,
        transfer_content=transfer_content,
        amount=amount,
    )
    enabled = sepay_svc.sepay_configured_for_qr()
    qr_url = None
    if enabled:
        qr_url = sepay_svc.build_sepay_qr_image_url(
            account_number=settings.SEPAY_QR_ACCOUNT_NUMBER,
            bank_code=settings.SEPAY_QR_BANK_CODE,
            amount=amount,
            des=transfer_content,
        )
    hook = (getattr(settings, "SEPAY_WEBHOOK_PUBLIC_URL", "") or "").strip().rstrip("/") or None
    if not hook:
        base = (settings.BACKEND_PUBLIC_URL or "").rstrip("/")
        hook = f"{base}/api/v1/sepay/webhook" if base else None
    return schemas.SepayDepositInfoResponse(
        enabled=enabled,
        transfer_content=transfer_content,
        amount=amount,
        qr_image_url=qr_url,
        bank_code=settings.SEPAY_QR_BANK_CODE or None,
        account_number=settings.SEPAY_QR_ACCOUNT_NUMBER or None,
        register_webhook_url=hook,
    )


@router.post("/{order_id}/pay-deposit", response_model=schemas.PaymentResponse)
def pay_deposit(
    order_id: int,
    payment_data: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Pay deposit for order
    """
    # 1. Get order
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # 2. Check permission
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 3. Check if deposit is required
    if not order.requires_deposit:
        raise HTTPException(status_code=400, detail="This order doesn't require deposit")
    
    # 4. Check if deposit already paid
    if order.deposit_paid >= order.deposit_amount:
        raise HTTPException(status_code=400, detail="Deposit already paid")
    
    # 5. Check payment amount
    if payment_data.amount != order.deposit_amount:
        raise HTTPException(
            status_code=400, 
            detail=f"Deposit amount must be {order.deposit_amount}"
        )
    
    # 6. Create payment record
    payment = crud.payment.create_payment(
        db=db,
        order_id=order_id,
        amount=payment_data.amount,
        payment_method=payment_data.payment_method.value,
        payment_type="deposit",
        bank_name=payment_data.bank_name,
        account_number=payment_data.account_number,
        account_name=payment_data.account_name,
        transaction_code=payment_data.transaction_code,
        transfer_date=payment_data.transfer_date
    )
    
    # 7. Update order status (still pending admin confirmation)
    order.payment_status = models.PaymentStatus.PENDING.value
    
    db.commit()
    db.refresh(payment)
    
    # 8. Send notification to admin
    # crud.notification.create_admin_notification(...)
    
    return payment

@router.post("/{order_id}/cancel", response_model=schemas.OrderResponse)
def cancel_order(
    order_id: int,
    reason: str = Query(..., description="Cancellation reason"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Cancel order
    """
    order = crud.order.cancel_order(
        db=db,
        order_id=order_id,
        user_id=current_user.id,
        reason=reason
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not authorized")
    
    return order

@router.post("/{order_id}/confirm-received", response_model=schemas.OrderResponse)
def confirm_received(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Khách hàng xác nhận đã nhận hàng (chuyển trạng thái Đang giao -> Đã nhận hàng)
    """
    order = crud.order.confirm_received(
        db=db,
        order_id=order_id,
        user_id=current_user.id
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or cannot confirm")
    recipient = order.customer_email or getattr(current_user, "email", None)
    if recipient:
        background_tasks.add_task(
            send_order_email,
            recipient,
            f"Đã xác nhận nhận hàng {order.order_code}",
            "Cảm ơn bạn đã xác nhận nhận hàng. Nếu có vấn đề, vui lòng liên hệ 188.com.vn.",
        )
    return order

@router.get("/{order_id}", response_model=schemas.OrderResponse)
def read_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get order detail"""
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return order

# ========== ADMIN ORDER ENDPOINTS ==========
@router.get("/admin/all", response_model=List[schemas.AdminOrderResponse])
def admin_get_orders(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    payment_status: Optional[str] = None,
    requires_deposit: Optional[bool] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
):
    """
    Admin: Get all orders with filters
    """
    return crud.order.get_orders_admin(
        db=db,
        skip=skip,
        limit=limit,
        status=status,
        payment_status=payment_status,
        requires_deposit=requires_deposit,
        date_from=date_from,
        date_to=date_to
    )

@router.get("/admin/stats", response_model=schemas.AdminOrderStats)
def admin_order_stats(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
    period: str = Query("today", pattern="^(today|week|month|year|all)$")
):
    """
    Admin: Get order statistics
    """
    return crud.order.get_order_stats(db, period=period)

@router.put("/admin/{order_id}", response_model=schemas.AdminOrderResponse)
def admin_update_order(
    order_id: int,
    order_update: schemas.OrderUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """
    Admin: Update order status
    """
    order_before = crud.order.get_order(db, order_id=order_id)
    if not order_before:
        raise HTTPException(status_code=404, detail="Order not found")
    old_status_val = getattr(order_before.status, "value", order_before.status)
    update_payload = order_update.model_dump(exclude_unset=True)

    order = crud.order.admin_update_order(
        db=db,
        order_id=order_id,
        order_update=order_update,
        admin_id=current_admin.id
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    new_status_val = getattr(order.status, "value", order.status)
    if update_payload.get("status") is not None and str(new_status_val) != str(old_status_val):
        recipient = order.customer_email or (order.user.email if order.user else None)
        if recipient:
            background_tasks.add_task(
                send_order_email,
                recipient,
                f"Cập nhật trạng thái đơn {order.order_code}",
                f"Đơn hàng của bạn đã được cập nhật trạng thái: {order.status}.",
            )
    return order

@router.post("/admin/{order_id}/confirm-deposit", response_model=schemas.AdminOrderResponse)
def admin_confirm_deposit(
    order_id: int,
    payment_data: schemas.PaymentConfirm,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """
    Admin: Confirm deposit payment
    """
    # 1. Confirm payment
    payment = crud.payment.confirm_payment(
        db=db,
        payment_id=payment_data.payment_id,
        admin_id=current_admin.id,
        is_confirmed=payment_data.is_confirmed,
        note=payment_data.confirmation_note
    )
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    # 2. Update order status
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if payment_data.is_confirmed:
        # Update deposit paid amount
        order.deposit_paid = payment.amount
        order.deposit_paid_at = datetime.now()
        
        # If deposit is 100%, mark as fully paid (assign enum, not .value)
        if order.deposit_type == DepositTypeEnum.PERCENT_100:
            order.payment_status = PaymentStatusEnum.PAID
            order.status = OrderStatusEnum.CONFIRMED
            order.confirmed_at = datetime.now()
        else:
            # 30% deposit, update status
            order.payment_status = PaymentStatusEnum.DEPOSIT_PAID
            order.status = OrderStatusEnum.DEPOSIT_PAID

        # Update remaining amount
        order.remaining_amount = order.total_amount - order.deposit_paid
    else:
        # Payment rejected
        order.status = OrderStatusEnum.WAITING_DEPOSIT
    
    db.commit()
    db.refresh(order)

    if payment_data.is_confirmed:
        background_tasks.add_task(send_deposit_confirmed_email_task, order_id)

    return order

@router.post("/admin/{order_id}/confirm-deposit-manual", response_model=schemas.AdminOrderResponse)
def admin_confirm_deposit_manual(
    order_id: int,
    background_tasks: BackgroundTasks,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """
    Admin: Xác nhận cọc khi chưa có giao dịch trong hệ thống (khách đã chuyển khoản nhưng không gửi form).
    Body: { "confirmation_note": "..." } (tùy chọn)
    """
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    status_val = getattr(order.status, "value", order.status)
    if status_val != OrderStatusEnum.WAITING_DEPOSIT.value:
        raise HTTPException(status_code=400, detail="Chỉ xác nhận được đơn đang chờ đặt cọc")
    amount_due = resolve_order_deposit_due(order)
    if not _admin_expected_deposit_rows(order) and _dec(order.deposit_amount) <= 0:
        raise HTTPException(status_code=400, detail="Đơn không yêu cầu cọc")
    if amount_due <= 0:
        raise HTTPException(
            status_code=400,
            detail="Không xác định được số tiền cọc — kiểm tra tổng đơn hoặc cập nhật loại / % đặt cọc",
        )

    stored_amt = _dec(order.deposit_amount)
    dt_val = getattr(order.deposit_type, "value", order.deposit_type)
    if stored_amt != amount_due:
        order.deposit_amount = amount_due
        if dt_val in (None, DepositTypeEnum.NONE.value, "", "none"):
            order.deposit_type = DepositTypeEnum.PERCENT_30
            order.deposit_percentage = 30

    order.deposit_paid = amount_due
    order.deposit_paid_at = datetime.now()
    order.remaining_amount = (_dec(order.total_amount) - amount_due).quantize(Decimal("0.01"))
    if order.deposit_type == DepositTypeEnum.PERCENT_100:
        order.payment_status = PaymentStatusEnum.PAID
        order.status = OrderStatusEnum.CONFIRMED
        order.confirmed_at = datetime.now()
    else:
        order.payment_status = PaymentStatusEnum.DEPOSIT_PAID
        order.status = OrderStatusEnum.DEPOSIT_PAID
    if body.get("confirmation_note"):
        order.admin_notes = (order.admin_notes or "") + "\n[Xác nhận cọc thủ công] " + str(body.get("confirmation_note"))
    db.commit()
    db.refresh(order)
    background_tasks.add_task(send_deposit_confirmed_email_task, order_id)
    return order


@router.get("/admin/{order_id}/payments", response_model=List[schemas.PaymentResponse])
def admin_get_order_payments(
    order_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """
    Admin: Get payments for order
    """
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return crud.payment.get_order_payments(db, order_id=order_id)