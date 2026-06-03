# backend/app/api/endpoints/orders.py - COMPLETE ORDER API WITH DEPOSIT
import io
import re
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status, BackgroundTasks, Header, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from app.db.session import get_db
from app import crud, models, schemas
from app.crud import promotion as crud_promotion
from app.crud.promotion import PromoValidationError
from app.models.order import OrderStatus as OrderStatusEnum, DepositType as DepositTypeEnum, PaymentStatus as PaymentStatusEnum
from app.core.security import get_current_user, get_current_user_optional, require_module_permission
from app.core.config import settings
from app.services.email_service import (
    deliver_deposit_confirmed_email,
    send_order_email,
    schedule_deposit_confirmed_email,
    send_order_created_email_task,
    send_order_received_confirmed_email_task,
)
from app.services import sepay as sepay_svc
from app.services import promotion_grants as grant_svc
from app.services.order_discounts import calculate_order_discounts
from app.services import affiliate_wallet as affiliate_svc
from app.services import order_shipment_timeline as shipment_svc
from app.services import order_shipper_notify as shipper_notify_svc
from app.services import ems_shipment_import as ems_import_svc
from app.services import ems_tracking_refresh as ems_refresh_svc
from app.services import ems_cod_settlement_import as cod_settlement_svc
from app.services import ems_freight_settlement_import as freight_settlement_svc
from app.services import shipping_operations as shipping_ops_svc
from app.services import shop_return_confirm as shop_return_confirm_svc
from app.services import ems_import_sample_templates as ems_sample_tpl_svc
from app.schemas import order_shipment as shipment_schemas


def _serialize_user_order(db: Session, order: models.Order) -> schemas.OrderResponse:
    base = schemas.OrderResponse.model_validate(order)
    return base.model_copy(
        update={"can_confirm_received": shipment_svc.can_customer_confirm_received(db, order)}
    )


def _serialize_user_orders(db: Session, orders: List[models.Order]) -> List[schemas.OrderResponse]:
    flags = shipment_svc.batch_can_confirm_received(db, orders)
    return [
        schemas.OrderResponse.model_validate(order).model_copy(
            update={"can_confirm_received": flags.get(order.id, False)}
        )
        for order in orders
    ]


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
        from app.services.warehouse_clearance import (
            is_warehouse_cart_product,
            resolve_checkout_line_prices,
        )

        items = []
        total_amount = Decimal('0')
        list_amount = Decimal('0')
        regular_subtotal = Decimal('0')
        regular_list_subtotal = Decimal('0')
        warehouse_subtotal = Decimal('0')
        requires_deposit = False
        warehouse_checkout_lines: list = []
        
        for item in order_data.items:
            product = crud.product.get_product(db, item.product_id)
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            if is_warehouse_cart_product(product):
                warehouse_checkout_lines.append((product, int(item.quantity or 0)))
            
            # Check if product requires deposit
            if product.deposit_require:
                requires_deposit = True
            
            unit_f, list_f = resolve_checkout_line_prices(db, product, user=current_user)
            unit_price = Decimal(str(unit_f))
            list_unit = Decimal(str(list_f))
            item_total = unit_price * item.quantity
            total_amount += item_total
            list_amount += list_unit * item.quantity
            if is_warehouse_cart_product(product):
                warehouse_subtotal += item_total
            else:
                regular_subtotal += item_total
                regular_list_subtotal += list_unit * item.quantity

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

        if warehouse_checkout_lines:
            from app.services.warehouse_stock import (
                WarehouseStockError,
                validate_warehouse_checkout_lines,
            )

            try:
                validate_warehouse_checkout_lines(db, warehouse_checkout_lines)
            except WarehouseStockError as exc:
                raise HTTPException(status_code=400, detail=exc.message) from exc
        
        # --- PROMO + BIRTHDAY + LOYALTY DISCOUNT (chỉ khi đã đăng nhập) ---
        birthday_discount_amount = Decimal('0')
        loyalty_discount_amount = Decimal('0')
        welcome_discount_amount = Decimal('0')
        discount_notes = []
        applied_promotion = None
        applied_grant_id = None

        if current_user is not None and regular_subtotal > 0:
            try:
                breakdown = calculate_order_discounts(
                    db,
                    user=current_user,
                    subtotal=regular_subtotal,
                    list_subtotal=regular_list_subtotal,
                    promo_code=order_data.promo_code,
                )
            except PromoValidationError as exc:
                raise HTTPException(status_code=400, detail=exc.message) from exc

            birthday_discount_amount = breakdown.birthday_discount_amount
            loyalty_discount_amount = breakdown.loyalty_discount_amount
            welcome_discount_amount = breakdown.welcome_discount_amount
            discount_notes = list(breakdown.discount_notes)
            applied_promotion = breakdown.applied_promotion
            applied_grant_id = breakdown.applied_grant_id
            
        # Apply discount (chỉ hàng thường — đồng bộ giỏ hàng)
        total_discount_amount = birthday_discount_amount + loyalty_discount_amount + welcome_discount_amount
        regular_after_discount = max(Decimal('0'), regular_subtotal - total_discount_amount)
        total_amount_after_discount = regular_after_discount + warehouse_subtotal

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
        order_total_before_wallet = total_amount_after_discount + shipping_fee

        referrer_user_id = affiliate_svc.resolve_order_referrer_user_id(
            db,
            user_id=current_user.id if current_user else None,
            referral_code=order_data.referral_code,
        )
        
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
            discount_amount=total_discount_amount,
            shipping_fee=shipping_fee,
            total_amount=order_total_before_wallet,
            admin_notes="\n".join(discount_notes),
            requires_deposit=requires_deposit,
            deposit_type=deposit_type.value if deposit_type else None,
            deposit_percentage=deposit_percentage,
            deposit_amount=deposit_amount,
            remaining_amount=order_total_before_wallet - deposit_amount,
            items=items,
            referrer_user_id=referrer_user_id,
        )

        if current_user is not None and applied_promotion and welcome_discount_amount > 0:
            grant_svc.mark_grant_used(
                db,
                user_id=current_user.id,
                promotion_id=applied_promotion.id,
                order_id=order.id,
            )
            crud_promotion.record_promotion_usage(
                db,
                promotion=applied_promotion,
                user_id=current_user.id,
                order_id=order.id,
                discount_amount=welcome_discount_amount,
                grant_id=applied_grant_id,
            )
            db.commit()
            db.refresh(order)

        wallet_note = ""
        if current_user is not None and order_data.wallet_amount and Decimal(str(order_data.wallet_amount)) > 0:
            used = affiliate_svc.apply_wallet_to_order(
                db,
                current_user.id,
                order,
                Decimal(str(order_data.wallet_amount)),
            )
            if used > 0:
                wallet_note = f"Thanh toán ví: -{used:,.0f} đ"
                discount_notes.append(wallet_note)
                order.admin_notes = "\n".join(discount_notes)

        if not requires_deposit:
            affiliate_svc.create_pending_commission_for_order(db, order)

        if shipment_svc.should_have_timeline(order):
            shipment_svc.ensure_shipment_timeline(db, order)

        if not requires_deposit:
            from app.services.warehouse_stock import (
                WarehouseStockError,
                reload_order_with_items,
                reserve_warehouse_stock_for_order,
            )

            order_loaded = reload_order_with_items(db, order.id)
            if order_loaded:
                try:
                    reserve_warehouse_stock_for_order(db, order_loaded)
                except WarehouseStockError as exc:
                    db.rollback()
                    raise HTTPException(status_code=400, detail=exc.message) from exc

        db.commit()
        db.refresh(order)
        
        # 5. If deposit required, set status to WAITING_DEPOSIT (use enum, not .value)
        if requires_deposit and _dec(order.total_amount) > 0:
            order.status = OrderStatusEnum.WAITING_DEPOSIT
            db.commit()
            db.refresh(order)
        
        if referrer_user_id:
            background_tasks.add_task(affiliate_svc.notify_referrer_new_order_task, order.id)
        
        recipient = order.customer_email or (getattr(current_user, "email", None) if current_user else None)
        if recipient:
            background_tasks.add_task(send_order_created_email_task, order.id)
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
    orders = crud.order.get_user_orders(
        db, user_id=current_user.id,
        skip=skip, limit=limit, status=status
    )
    return _serialize_user_orders(db, orders)

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


@router.get("/{order_id}/deposit-qr-image")
def download_deposit_qr_image(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Tải ảnh QR cọc qua backend (tránh CORS từ qr.sepay.vn / vietqr.io trên trình duyệt)."""
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

    qr_url = sepay_svc.resolve_deposit_qr_image_url(db, order)
    if not qr_url:
        raise HTTPException(status_code=404, detail="Không tạo được mã QR")

    try:
        raw = sepay_svc.fetch_qr_image_bytes(qr_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Không tải được ảnh QR") from exc

    safe_code = re.sub(r"[^\w.-]+", "_", (order.order_code or f"don-{order_id}").strip()) or str(order_id)
    return Response(
        content=raw,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="qr-chuyen-khoan-{safe_code}.png"'},
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
    Khách hàng xác nhận đã nhận hàng (chỉ khi bước awaiting_confirm đang active)
    """
    order = crud.order.get_order_with_items(db, order_id=order_id)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    if not shipment_svc.can_customer_confirm_received(db, order):
        raise HTTPException(
            status_code=400,
            detail="Đơn hàng chưa sẵn sàng để xác nhận nhận hàng. Vui lòng đợi 188.com.vn hoàn tất giao hàng.",
        )
    order = crud.order.confirm_received(
        db=db,
        order_id=order_id,
        user_id=current_user.id
    )
    if not order:
        raise HTTPException(status_code=400, detail="Không thể xác nhận đơn hàng lúc này")
    background_tasks.add_task(shipper_notify_svc.notify_customer_delivered_with_review, order.id)
    background_tasks.add_task(send_order_received_confirmed_email_task, order.id)
    return order

@router.get("/{order_id}/shipment-timeline", response_model=shipment_schemas.OrderShipmentTimelineResponse)
def get_order_shipment_timeline(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = crud.order.get_order(db, order_id=order_id)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Order not found")
    payload = shipment_svc.get_timeline_payload(db, order)
    db.commit()
    return payload


@router.get("/{order_id}", response_model=schemas.OrderResponse)
def read_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get order detail"""
    order = crud.order.get_order_with_items(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return _serialize_user_order(db, order)

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
    period: str = Query("today", pattern="^(today|week|month|year|all)$"),
    preset: Optional[str] = Query(
        None,
        description="today | this_week | last_week | this_month | last_month",
    ),
    date: Optional[str] = Query(None, description="Một ngày cụ thể (YYYY-MM-DD)"),
    year: Optional[int] = Query(None, ge=1970, le=2100),
    date_from: Optional[str] = Query(None, description="Từ ngày (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Đến ngày (YYYY-MM-DD)"),
):
    """
    Admin: thống kê đơn + doanh thu theo ngày/tuần/tháng/năm hoặc khoảng ngày tùy chọn.
    """
    try:
        return crud.order.get_order_stats(
            db,
            period=period,
            preset=preset,
            on_date=date,
            year=year,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/lookup-by-code/{order_code}", response_model=schemas.AdminOrderResponse)
def admin_lookup_order_by_code(
    order_code: str,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tra cứu đơn theo mã DHxxx (dùng từ trang vận chuyển EMS)."""
    code = order_code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Thiếu mã đơn")
    order = crud.order.get_order_by_code(db, code)
    if not order:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {code} trên 188.com.vn")
    return order


@router.get("/admin/shipping/ems-records", response_model=shipment_schemas.EmsShippingImportResponse)
def admin_list_ems_shipping_records(
    skip: int = 0,
    limit: int = 50,
    sync_status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách bảng quản lý vận chuyển EMS đã lưu (phân trang + tra cứu)."""
    return ems_import_svc.list_ems_shipping_records(
        db,
        skip=skip,
        limit=limit,
        sync_status=sync_status,
        search=q,
    )


@router.get(
    "/admin/shipping/ems-import-batches",
    response_model=shipment_schemas.EmsShippingImportBatchesListResponse,
)
def admin_list_ems_import_batches(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách các lần import file gửi EMS — mở lại báo cáo từng lần."""
    return ems_import_svc.list_ems_import_batches(db, limit=limit)


@router.get("/admin/shipping/ems-import/sample")
def admin_download_ems_shipment_import_sample(
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tải file Excel mẫu import gửi EMS (file gui ems.xlsx)."""
    content, filename = ems_sample_tpl_svc.build_ems_shipment_sample_xlsx()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/shipping/ems-import", response_model=shipment_schemas.EmsShippingImportResponse)
async def admin_import_ems_shipment_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Import file gui ems.xlsx — cột A mã vận đơn, I đơn hàng (DHxxx), G COD, D tên khách."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel .xlsx")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File trống.")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File quá lớn (tối đa 10MB).")

    try:
        payload = ems_import_svc.import_ems_shipment_excel(
            db,
            raw,
            admin_id=current_admin.id,
            source_filename=file.filename,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Không đọc được file Excel: {exc}") from exc

    return payload


@router.post(
    "/admin/shipping/ems-tracking-refresh/resume/{job_id}",
    response_model=shipment_schemas.EmsTrackingRefreshJobResponse,
)
def admin_resume_ems_tracking_refresh_job(
    job_id: str,
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tiếp tục job tra EMS bị dừng giữa chừng (worker crash / restart server)."""
    job = ems_refresh_svc.resume_tracking_refresh_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job tra EMS.")
    return job


@router.get(
    "/admin/shipping/ems-tracking-refresh/active",
    response_model=shipment_schemas.EmsTrackingRefreshActiveResponse,
)
def admin_get_active_ems_tracking_refresh_job(
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Job tra EMS đang chạy gần nhất (queued/running) — dùng khi F5 trang admin."""
    job = ems_refresh_svc.get_active_tracking_refresh_job()
    if not job:
        return shipment_schemas.EmsTrackingRefreshActiveResponse(active=False, job=None)
    return shipment_schemas.EmsTrackingRefreshActiveResponse(active=True, job=job)


@router.get(
    "/admin/shipping/ems-tracking-refresh/job/{job_id}",
    response_model=shipment_schemas.EmsTrackingRefreshJobResponse,
)
def admin_get_ems_tracking_refresh_job(
    job_id: str,
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Poll tiến trình tra EMS nền sau import / cron."""
    job = ems_refresh_svc.get_tracking_refresh_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy job tra EMS.")
    return job


@router.post(
    "/admin/shipping/ems-tracking-refresh",
    response_model=shipment_schemas.EmsTrackingRefreshEnqueueResponse,
)
def admin_enqueue_ems_tracking_refresh(
    body: shipment_schemas.EmsTrackingRefreshRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tra lại EMS cho dòng đã chọn, kết quả tìm kiếm, hoặc bộ lọc trạng thái (chạy nền)."""
    ids = [int(x) for x in (body.ids or []) if int(x) > 0]
    search_q = (body.q or "").strip()
    filter_status = (body.sync_status or "").strip()

    if not ids:
        if search_q:
            ids = ems_import_svc.collect_record_ids_for_refresh(
                db,
                search=search_q,
                sync_status=filter_status if filter_status and filter_status != "all" else None,
                non_terminal_only=bool(body.non_terminal_only),
            )
        elif filter_status and filter_status != "all":
            ids = ems_import_svc.collect_record_ids_for_refresh(
                db,
                sync_status=filter_status,
                non_terminal_only=bool(body.non_terminal_only),
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Chọn dòng, nhập mã tra cứu, hoặc chọn bộ lọc trạng thái.",
            )

    if not ids:
        if search_q and body.non_terminal_only:
            return {
                "ok": True,
                "job_id": None,
                "queued": 0,
                "message": "Đơn đã hoàn tất — không cần tra EMS lại.",
            }
        raise HTTPException(status_code=404, detail="Không tìm thấy dòng vận chuyển nào để tra EMS.")

    job_id = ems_refresh_svc.enqueue_tracking_refresh(
        ids,
        admin_id=current_admin.id,
        source="manual_search" if search_q else "manual",
    )
    label = f"«{search_q}»" if search_q else f"{len(ids)} dòng"
    return {
        "ok": True,
        "job_id": job_id,
        "queued": len(ids),
        "message": f"Đã xếp hàng tra EMS cho {label}.",
    }


@router.delete("/admin/shipping/ems-records", response_model=shipment_schemas.EmsShippingDeleteResponse)
def admin_delete_ems_shipping_records(
    body: shipment_schemas.EmsShippingDeleteRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Xóa vĩnh viễn các dòng khỏi bảng vận chuyển EMS."""
    deleted = ems_import_svc.delete_ems_shipping_records(db, body.ids)
    return {"ok": True, "deleted": deleted}


@router.get(
    "/admin/shipping/cod-settlement-batches",
    response_model=shipment_schemas.EmsCodSettlementImportResponse,
)
def admin_list_cod_settlement_batches(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách các lần import đối soát COD đã thanh toán."""
    return cod_settlement_svc.list_cod_settlement_batches(db)


@router.get("/admin/shipping/cod-settlement-import/sample")
def admin_download_cod_settlement_import_sample(
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tải file Excel mẫu đối soát COD EMS trả shop."""
    content, filename = ems_sample_tpl_svc.build_cod_settlement_sample_xlsx()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/admin/shipping/cod-settlement-import",
    response_model=shipment_schemas.EmsCodSettlementImportResponse,
)
async def admin_import_cod_settlement_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Import file Doi soat cod — cột C mã vận chuyển EMS, cột D số tiền đã trả, E1 ngày trả tiền."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xls", ".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel .xls / .xlsx")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File trống.")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File quá lớn (tối đa 10MB).")

    try:
        payload = cod_settlement_svc.import_cod_settlement_excel(
            db,
            raw,
            admin_id=current_admin.id,
            source_filename=file.filename,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Không đọc được file đối soát COD: {exc}") from exc

    return payload


@router.get("/admin/shipping/operations-stats")
def admin_shipping_operations_stats(
    view: str | None = None,
    granularity: str = "month",
    limit: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    preset: str | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Thống kê vận hành hoặc timeline (`view=timeline`)."""
    if (view or "").strip().lower() == "timeline":
        try:
            return shipping_ops_svc.get_shipping_timeline_stats(
                db,
                granularity=granularity,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
                preset=preset,
                year=year,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return shipping_ops_svc.get_shipping_operations_stats(db)


@router.get(
    "/admin/shipping/operations-stats/timeline",
    response_model=shipment_schemas.EmsShippingTimelineStatsResponse,
)
def admin_shipping_timeline_stats(
    granularity: str = "month",
    limit: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    preset: str | None = None,
    year: int | None = None,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Thống kê vận đơn EMS theo năm / tháng / tuần / ngày (theo ngày import)."""
    try:
        return shipping_ops_svc.get_shipping_timeline_stats(
            db,
            granularity=granularity,
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            preset=preset,
            year=year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/admin/shipping/operations-stats/records",
    response_model=shipment_schemas.EmsShippingOperationsRecordsResponse,
)
def admin_shipping_operations_records(
    bucket: str,
    skip: int = 0,
    limit: int = 25,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách vận đơn EMS theo nhóm thống kê vận hành."""
    try:
        return shipping_ops_svc.list_operations_bucket_records(
            db,
            bucket,
            skip=skip,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/admin/shipping/operations-stats/timeline/records",
    response_model=shipment_schemas.EmsShippingOperationsRecordsResponse,
)
def admin_shipping_timeline_records(
    bucket: str,
    granularity: str = "week",
    period_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    preset: str | None = None,
    year: int | None = None,
    skip: int = 0,
    limit: int = 25,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách vận đơn EMS theo kỳ timeline và nhóm thống kê."""
    try:
        return shipping_ops_svc.list_timeline_bucket_records(
            db,
            bucket,
            granularity=granularity,
            period_key=period_key,
            date_from=date_from,
            date_to=date_to,
            preset=preset,
            year=year,
            skip=skip,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/admin/{order_id}/approve-return-received", response_model=schemas.AdminOrderResponse)
def admin_approve_return_received(
    order_id: int,
    body: shipment_schemas.AdminApproveReturnReceivedIn,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Shop xác nhận đã nhận hàng hoàn — hủy hoa hồng affiliate."""
    try:
        order = shipping_ops_svc.admin_approve_return_received(
            db,
            order_id,
            admin_id=current_admin.id,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return order


@router.post(
    "/admin/shipping/shop-return-preview",
    response_model=shipment_schemas.ShopReturnConfirmResponse,
)
def admin_preview_shop_returns_bulk(
    body: shipment_schemas.ShopReturnConfirmRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tra cứu trạng thái EMS/đơn — không xác nhận."""
    del current_admin
    text = (body.text or "").strip()
    codes = [str(c).strip() for c in (body.order_codes or []) if str(c).strip()]
    if not text and not codes:
        raise HTTPException(status_code=400, detail="Nhập ít nhất một mã.")
    try:
        if text:
            return shop_return_confirm_svc.preview_shop_returns_from_text(db, text)
        return shop_return_confirm_svc.preview_shop_returns_from_text(db, "\n".join(codes))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/admin/shipping/shop-return-confirm",
    response_model=shipment_schemas.ShopReturnConfirmResponse,
)
def admin_confirm_shop_returns_bulk(
    body: shipment_schemas.ShopReturnConfirmRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Xác nhận đơn hoàn đã trả shop — nhập / dán danh sách mã DHxxx."""
    text = (body.text or "").strip()
    codes = [str(c).strip() for c in (body.order_codes or []) if str(c).strip()]
    if not text and not codes:
        raise HTTPException(status_code=400, detail="Nhập ít nhất một mã đơn (DHxxx).")
    try:
        if text:
            return shop_return_confirm_svc.confirm_shop_returns_from_text(
                db,
                text,
                admin_id=current_admin.id,
                note=body.note,
            )
        return shop_return_confirm_svc.confirm_shop_returns_from_text(
            db,
            "\n".join(codes),
            admin_id=current_admin.id,
            note=body.note,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/admin/shipping/resolve-return-warehouse-sku",
    response_model=shipment_schemas.ResolveReturnWarehouseSkuResponse,
)
def admin_resolve_return_warehouse_sku(
    code: str = Query(..., min_length=1, description="Mã EMS / tham chiếu / DHxxx"),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Trích mã SKU cột H file EMS → điền ô nhập kho thanh lý."""
    data = shop_return_confirm_svc.resolve_warehouse_sku_for_return_intake(db, code)
    return shipment_schemas.ResolveReturnWarehouseSkuResponse(**data)


@router.get(
    "/admin/shipping/return-warehouse-lookup",
    response_model=shipment_schemas.ReturnWarehouseLookupResponse,
)
def admin_return_warehouse_lookup(
    sku: str = Query(..., min_length=1, description="Mã SKU gốc hoặc mã kho H0723/40/3"),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tra cứu màu/size của SKU để nhập hàng hoàn vào kho thanh lý."""
    from app.services import return_warehouse_intake as rw_intake_svc

    try:
        data = rw_intake_svc.lookup_return_intake_catalog(db, sku)
        return shipment_schemas.ReturnWarehouseLookupResponse(**data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/admin/shipping/return-warehouse-intake",
    response_model=shipment_schemas.ReturnWarehouseIntakeResponse,
)
def admin_return_warehouse_intake(
    body: shipment_schemas.ReturnWarehouseIntakeRequest,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Nhập hàng hoàn vào kho thanh lý — tạo/cộng tồn dòng is_warehouse_clearance."""
    from app.services import return_warehouse_intake as rw_intake_svc

    try:
        result = rw_intake_svc.intake_return_to_warehouse(
            db,
            base_sku=body.sku,
            color=body.color,
            size=body.size or "",
            quantity=body.quantity,
            color_index=body.color_index,
            color_image=body.color_image,
            warehouse_product_id=body.warehouse_product_id,
            admin_id=current_admin.id,
        )
        pid = result["product_id"]
        msg = (
            f"Đã cộng {result['quantity_added']} vào tồn «{pid}» "
            f"(tồn {result['available_before']} → {result['available_after']})."
            if result["action"] == "updated"
            else f"Đã tạo dòng kho thanh lý «{pid}» với tồn {result['available_after']}."
        )
        return shipment_schemas.ReturnWarehouseIntakeResponse(
            ok=True,
            action=result["action"],
            product_id=pid,
            available_before=result["available_before"],
            available_after=result["available_after"],
            quantity_added=result["quantity_added"],
            message=msg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/shipping/shop-return-confirm-import/sample")
def admin_download_shop_return_confirm_import_sample(
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tải file Excel mẫu xác nhận đơn hoàn đã trả shop."""
    content, filename = ems_sample_tpl_svc.build_shop_return_confirm_sample_xlsx()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/admin/shipping/shop-return-confirm-import",
    response_model=shipment_schemas.ShopReturnConfirmResponse,
)
async def admin_confirm_shop_returns_excel(
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Import Excel xác nhận đơn hoàn đã trả shop — cột có mã DHxxx; mã không tồn tại báo lỗi."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm", ".xls")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel .xls / .xlsx")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File trống.")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File quá lớn (tối đa 5MB).")

    try:
        return shop_return_confirm_svc.confirm_shop_returns_from_excel(
            db,
            raw,
            admin_id=current_admin.id,
            note=(note or "").strip() or None,
            source_filename=file.filename,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Không xử lý được file: {exc}") from exc


@router.get(
    "/admin/shipping/freight-settlement-batches",
    response_model=shipment_schemas.EmsFreightSettlementImportResponse,
)
def admin_list_freight_settlement_batches(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Danh sách các lần import đối soát cước EMS."""
    return freight_settlement_svc.list_freight_settlement_batches(db)


@router.get("/admin/shipping/freight-settlement-import/sample")
def admin_download_freight_settlement_import_sample(
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Tải file Excel mẫu đối soát cước EMS."""
    content, filename = ems_sample_tpl_svc.build_freight_settlement_sample_xlsx()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/admin/shipping/freight-settlement-import",
    response_model=shipment_schemas.EmsFreightSettlementImportResponse,
)
async def admin_import_freight_settlement_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Import file Doi soat cuoc — cột A mã vận chuyển EMS, cột L cước phí."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xls", ".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file Excel .xls / .xlsx")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="File trống.")
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File quá lớn (tối đa 10MB).")

    try:
        payload = freight_settlement_svc.import_freight_settlement_excel(
            db,
            raw,
            admin_id=current_admin.id,
            source_filename=file.filename,
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Không đọc được file đối soát cước: {exc}") from exc

    return payload


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
        deposit_confirmed_statuses = {
            OrderStatusEnum.DEPOSIT_PAID.value,
            OrderStatusEnum.CONFIRMED.value,
        }
        if (
            str(old_status_val) == OrderStatusEnum.WAITING_DEPOSIT.value
            and str(new_status_val) in deposit_confirmed_statuses
        ):
            schedule_deposit_confirmed_email(order_id)
        recipient = order.customer_email or (order.user.email if order.user else None)
        if recipient:
            background_tasks.add_task(
                send_order_email,
                recipient,
                f"Cập nhật trạng thái đơn {order.order_code}",
                f"Đơn hàng của bạn đã được cập nhật trạng thái: {order.status}.",
            )
    return order

@router.post("/admin/{order_id}/confirm-deposit", response_model=schemas.AdminOrderDepositConfirmOut)
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
        dt_val = getattr(order.deposit_type, "value", order.deposit_type)
        if dt_val == DepositTypeEnum.PERCENT_100.value:
            order.payment_status = PaymentStatusEnum.PAID
            order.status = OrderStatusEnum.CONFIRMED
            order.confirmed_at = datetime.now()
        else:
            # 30% deposit, update status
            order.payment_status = PaymentStatusEnum.DEPOSIT_PAID
            order.status = OrderStatusEnum.DEPOSIT_PAID

        # Update remaining amount
        order.remaining_amount = order.total_amount - order.deposit_paid
        commission = affiliate_svc.grant_deposit_commission_for_order(db, order)
        shipment_svc.ensure_shipment_timeline(db, order)
        from app.services.warehouse_stock import (
            WarehouseStockError,
            reload_order_with_items,
            reserve_warehouse_stock_for_order,
        )

        order_loaded = reload_order_with_items(db, order.id)
        if order_loaded:
            try:
                reserve_warehouse_stock_for_order(db, order_loaded)
            except WarehouseStockError as exc:
                db.rollback()
                raise HTTPException(status_code=400, detail=exc.message) from exc
    else:
        # Payment rejected
        order.status = OrderStatusEnum.WAITING_DEPOSIT
        commission = None
    
    db.commit()
    db.refresh(order)

    deposit_email_out = schemas.DepositConfirmedEmailOut(
        sent=False,
        to=None,
        detail="Chưa gửi email (cọc chưa được xác nhận)",
    )
    if payment_data.is_confirmed:
        raw_email = deliver_deposit_confirmed_email(order_id)
        deposit_email_out = schemas.DepositConfirmedEmailOut(**raw_email)
        if commission:
            background_tasks.add_task(affiliate_svc.notify_referrer_deposit_commission_task, order_id)

    return schemas.AdminOrderDepositConfirmOut(order=order, deposit_email=deposit_email_out)

@router.post("/admin/{order_id}/confirm-deposit-manual", response_model=schemas.AdminOrderDepositConfirmOut)
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
    dt_val_after = getattr(order.deposit_type, "value", order.deposit_type)
    if dt_val_after == DepositTypeEnum.PERCENT_100.value:
        order.payment_status = PaymentStatusEnum.PAID
        order.status = OrderStatusEnum.CONFIRMED
        order.confirmed_at = datetime.now()
    else:
        order.payment_status = PaymentStatusEnum.DEPOSIT_PAID
        order.status = OrderStatusEnum.DEPOSIT_PAID
    commission = affiliate_svc.grant_deposit_commission_for_order(db, order)
    shipment_svc.ensure_shipment_timeline(db, order)
    if body.get("confirmation_note"):
        order.admin_notes = (order.admin_notes or "") + "\n[Xác nhận cọc thủ công] " + str(body.get("confirmation_note"))
    from app.services.warehouse_stock import (
        WarehouseStockError,
        reload_order_with_items,
        reserve_warehouse_stock_for_order,
    )

    order_loaded = reload_order_with_items(db, order.id)
    if order_loaded:
        try:
            reserve_warehouse_stock_for_order(db, order_loaded)
        except WarehouseStockError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=exc.message) from exc
    db.commit()
    db.refresh(order)
    raw_email = deliver_deposit_confirmed_email(order_id)
    deposit_email_out = schemas.DepositConfirmedEmailOut(**raw_email)
    if commission:
        background_tasks.add_task(affiliate_svc.notify_referrer_deposit_commission_task, order_id)
    return schemas.AdminOrderDepositConfirmOut(order=order, deposit_email=deposit_email_out)


@router.post("/admin/{order_id}/refund-deposit", response_model=schemas.AdminOrderResponse)
def admin_refund_deposit(
    order_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """
    Admin: duyệt trả cọc cho đơn đã đặt cọc.
    Khi hoàn cọc, hoa hồng affiliate của đơn sẽ bị thu hồi.
    Body: { "refund_note": "..." } (tùy chọn)
    """
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if _dec(order.deposit_paid) <= 0:
        raise HTTPException(status_code=400, detail="Đơn chưa ghi nhận tiền cọc")

    note = (str(body.get("refund_note") or body.get("reason") or "").strip() or "Đã duyệt trả cọc")
    for payment in crud.payment.get_order_payments(db, order_id=order.id):
        payment_type = (payment.payment_type or "").lower()
        if "deposit" in payment_type:
            payment.payment_status = PaymentStatusEnum.REFUNDED
            payment.confirmation_note = note

    order.payment_status = PaymentStatusEnum.REFUNDED
    order.status = OrderStatusEnum.CANCELLED
    order.cancelled_reason = note
    order.cancelled_at = datetime.now()
    order.processed_by = current_admin.id
    order.updated_at = datetime.now()
    order.admin_notes = ((order.admin_notes or "") + f"\n[Hoàn cọc] {note}").strip()
    affiliate_svc.handle_order_payment_status_change(db, order, PaymentStatusEnum.REFUNDED)

    db.commit()
    db.refresh(order)
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


@router.get("/admin/{order_id}/shipment-timeline", response_model=shipment_schemas.OrderShipmentTimelineResponse)
def admin_get_order_shipment_timeline(
    order_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    order = crud.order.get_order(db, order_id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    payload = shipment_svc.get_timeline_payload(db, order)
    db.commit()
    return payload


@router.post("/admin/{order_id}/shipment/clear-customs", response_model=schemas.AdminOrderResponse)
def admin_clear_customs_shipment(
    order_id: int,
    payload: shipment_schemas.AdminClearCustomsIn,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    try:
        order = shipment_svc.admin_clear_customs_and_ship(
            db,
            order_id,
            current_admin.id,
        )
        db.commit()
        db.refresh(order)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/{order_id}/shipment/mark-out-for-confirm", response_model=schemas.AdminOrderResponse)
def admin_mark_out_for_customer_confirm(
    order_id: int,
    payload: shipment_schemas.AdminMarkOutForConfirmIn,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("orders")),
):
    """Shop đóng hàng & gửi shipper — mở nút «Đã nhận hàng» cho khách."""
    try:
        order = shipment_svc.admin_mark_out_for_customer_confirm(
            db,
            order_id,
            current_admin.id,
            tracking_number=payload.tracking_number,
            shipping_provider=payload.shipping_provider,
        )
        db.commit()
        db.refresh(order)
        return order
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _require_shipment_cron_secret(authorization: Optional[str]) -> None:
    expected = (settings.CRON_SECRET or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/cron/advance-shipment-timelines")
def cron_advance_shipment_timelines(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    _require_shipment_cron_secret(authorization)
    advanced = shipment_svc.advance_auto_milestones_batch(db)
    return {"ok": True, "advanced": advanced}


@router.get("/cron/refresh-ems-tracking", response_model=shipment_schemas.EmsTrackingRefreshEnqueueResponse)
def cron_refresh_ems_tracking(
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """
    Cron tra EMS — đơn đang vận chuyển (chưa delivered/COD xong).
    Khuyến nghị 2 lần/ngày (sáng + chiều), ví dụ crontab:
      0 6,15 * * * curl -H "Authorization: Bearer $CRON_SECRET" ...
    """
    _require_shipment_cron_secret(authorization)
    return ems_refresh_svc.run_daily_ems_tracking_refresh(db)