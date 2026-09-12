"""Checkout fulfillment: định giá một lần, tách nguồn và tạo đơn nguyên tử."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.crud import promotion as crud_promotion
from app.crud.cart import _resolve_cart_line_image, cart as cart_crud
from app.crud.promotion import PromoValidationError
from app.models.order import PaymentMethod as PaymentMethodEnum
from app.core.config import settings
from app.services import affiliate_wallet as affiliate_svc
from app.services import order_shipment_timeline as shipment_svc
from app.services.email_service import send_order_created_email_task
from app.services.fulfillment_routing import (
    FULFILLMENT_CHINA,
    FULFILLMENT_VIETNAM,
    allocate_decimal_total,
    fulfillment_source_from_url,
    source_platform_from_url,
)
from app.services.order_discounts import calculate_order_discounts
from app.services import promotion_grants as grant_svc


def _dec(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def group_checkout_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Nhóm ổn định VN trước, TQ sau để quy tắc làm tròn luôn xác định."""
    return {
        source: rows
        for source in (FULFILLMENT_VIETNAM, FULFILLMENT_CHINA)
        if (rows := [row for row in items if row["fulfillment_source"] == source])
    }


def allocate_group_wallet(
    wallet_total: Decimal,
    group_totals: dict[str, Decimal],
    ordered_sources: list[str],
) -> dict[str, Decimal]:
    usable = min(
        max(Decimal("0"), wallet_total),
        sum((max(Decimal("0"), group_totals.get(key, Decimal("0"))) for key in ordered_sources), Decimal("0")),
    )
    return allocate_decimal_total(usable, group_totals, ordered_sources)


def build_group_financial_plan(
    rows: list[dict[str, Any]],
    *,
    discount: Decimal,
    shipping_fee: Decimal,
    requested_deposit_type: Optional[str],
) -> dict[str, Any]:
    subtotal = sum((_dec(row["total_price"]) for row in rows), Decimal("0"))
    discounted_subtotal = max(Decimal("0"), subtotal - discount)
    total = discounted_subtotal + shipping_fee
    requires_deposit = any(bool(row.get("requires_deposit")) for row in rows)
    deposit_type = requested_deposit_type
    if requires_deposit and not deposit_type:
        deposit_type = schemas.DepositType.PERCENT_30.value
    if deposit_type == schemas.DepositType.NONE.value:
        requires_deposit = False

    percentage = 0
    deposit = Decimal("0")
    if requires_deposit:
        if deposit_type == schemas.DepositType.PERCENT_100.value:
            percentage = 100
            deposit = discounted_subtotal
        else:
            deposit_type = schemas.DepositType.PERCENT_30.value
            percentage = 30
            deposit = (discounted_subtotal * Decimal("0.3")).quantize(Decimal("0.01"))
    return {
        "subtotal": subtotal,
        "discounted_subtotal": discounted_subtotal,
        "shipping_fee": shipping_fee,
        "total": total,
        "requires_deposit": requires_deposit,
        "deposit_type": deposit_type,
        "deposit_percentage": percentage,
        "deposit_amount": deposit,
        "remaining_amount": total - deposit,
        "initial_status": "waiting_deposit" if requires_deposit else "confirmed",
    }


def _serialize_order(db: Session, order: models.Order) -> schemas.OrderResponse:
    return schemas.OrderResponse.model_validate(order).model_copy(
        update={"can_confirm_received": shipment_svc.can_customer_confirm_received(db, order)}
    )


def create_checkout_fulfillment(
    *,
    db: Session,
    order_data: schemas.OrderCreate,
    current_user: Optional[models.User],
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Tạo một hoặc hai đơn trong cùng transaction; lỗi bất kỳ sẽ rollback toàn bộ."""
    if not order_data.items:
        raise HTTPException(status_code=400, detail="Đơn hàng phải có ít nhất một sản phẩm.")

    from app.services.google_automated_discount import (
        GoogleAutomatedDiscountError,
        apply_google_discount_to_cart_line,
        read_google_discount_lock,
    )
    from app.services.warehouse_clearance import (
        is_warehouse_cart_product,
        resolve_checkout_line_prices,
    )
    from app.services.warehouse_stock import (
        WarehouseStockError,
        reload_order_with_items,
        reserve_warehouse_stock_for_order,
        validate_warehouse_checkout_lines,
    )

    cart_lines_by_key: dict[tuple[Any, ...], Any] = {}
    if current_user is not None:
        for cart_item in cart_crud.get_user_cart_items(db, user_id=current_user.id):
            key = (
                int(cart_item.product_id),
                (cart_item.selected_size or "").strip() or None,
                (cart_item.selected_color or "").strip() or None,
            )
            cart_lines_by_key[key] = cart_item

    items: list[dict[str, Any]] = []
    regular_subtotal = Decimal("0")
    regular_list_subtotal = Decimal("0")
    warehouse_subtotal = Decimal("0")
    vietnam_stock_lines: list[tuple[Any, int]] = []

    for requested in order_data.items:
        product = crud.product.get_product(db, requested.product_id)
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {requested.product_id} not found")

        source_url = (product.link_default or "").strip() or None
        fulfillment_source = fulfillment_source_from_url(source_url)
        if fulfillment_source == FULFILLMENT_VIETNAM:
            vietnam_stock_lines.append((product, int(requested.quantity or 0)))

        unit_f, list_f = resolve_checkout_line_prices(db, product, user=current_user)
        cart_key = (
            int(product.id),
            (requested.selected_size or "").strip() or None,
            (requested.selected_color or "").strip() or None,
        )
        cart_line = cart_lines_by_key.get(cart_key)
        cart_pd = (
            dict(cart_line.product_data or {})
            if cart_line and isinstance(cart_line.product_data, dict)
            else {}
        )
        google_lock = (
            read_google_discount_lock(cart_pd)
            if not is_warehouse_cart_product(product)
            else None
        )
        if google_lock:
            unit_f = float(google_lock["price"])
            list_f = float(google_lock.get("prior_price") or list_f or unit_f)
        elif (requested.google_pv2_token or "").strip() and not is_warehouse_cart_product(product):
            try:
                unit_f, list_f, _ = apply_google_discount_to_cart_line(
                    product=product,
                    unit_sale=float(unit_f),
                    list_original=float(list_f),
                    product_data={},
                    google_pv2_token=requested.google_pv2_token,
                )
            except GoogleAutomatedDiscountError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        unit_price = Decimal(str(unit_f))
        list_unit = Decimal(str(list_f))
        item_total = unit_price * requested.quantity
        is_warehouse = is_warehouse_cart_product(product)
        if is_warehouse:
            warehouse_subtotal += item_total
        else:
            regular_subtotal += item_total
            regular_list_subtotal += list_unit * requested.quantity

        line_image = ""
        if cart_line:
            line_image = (cart_line.product_image or "").strip() or (
                cart_pd.get("main_image") or ""
            ).strip()
        if not line_image:
            color = (requested.selected_color or requested.selected_color_name or "").strip() or None
            if not color and cart_line:
                color = (
                    cart_line.selected_color or cart_line.selected_color_name or ""
                ).strip() or None
            line_image = _resolve_cart_line_image(
                product, color, cart_pd if cart_line else {}
            )

        items.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "product_image": line_image or (product.main_image or ""),
                "unit_price": unit_price,
                "quantity": requested.quantity,
                "total_price": item_total,
                "selected_size": requested.selected_size,
                "selected_color": requested.selected_color,
                "selected_color_name": requested.selected_color_name,
                "requires_deposit": product.deposit_require,
                "deposit_amount": unit_price * Decimal("0.3") if product.deposit_require else Decimal("0"),
                "fulfillment_source": fulfillment_source,
                "source_platform": source_platform_from_url(source_url),
                "source_url": source_url,
                "product_sku_snapshot": product.code,
                "is_warehouse_item": is_warehouse,
            }
        )

    try:
        validate_warehouse_checkout_lines(db, vietnam_stock_lines)
    except WarehouseStockError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    discount_notes: list[str] = []
    applied_promotion = None
    applied_grant_id = None
    total_discount = Decimal("0")
    welcome_discount = Decimal("0")
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
        total_discount = (
            breakdown.birthday_discount_amount
            + breakdown.loyalty_discount_amount
            + breakdown.welcome_discount_amount
        )
        welcome_discount = breakdown.welcome_discount_amount
        discount_notes = list(breakdown.discount_notes)
        applied_promotion = breakdown.applied_promotion
        applied_grant_id = breakdown.applied_grant_id

    after_discount = max(Decimal("0"), regular_subtotal - total_discount) + warehouse_subtotal
    charged_shipping_fee = Decimal("30000") if after_discount < Decimal("500000") else Decimal("0")
    grouped = group_checkout_items(items)
    sources = list(grouped)
    checkout_group_id = str(uuid.uuid4())

    regular_weights = {
        source: sum(
            (row["total_price"] for row in rows if not row["is_warehouse_item"]),
            Decimal("0"),
        )
        for source, rows in grouped.items()
    }
    discounts = allocate_decimal_total(total_discount, regular_weights, sources)
    shipping_source = (
        FULFILLMENT_VIETNAM
        if FULFILLMENT_VIETNAM in grouped
        else FULFILLMENT_CHINA
    )
    referrer_user_id = affiliate_svc.resolve_order_referrer_user_id(
        db,
        user_id=current_user.id if current_user else None,
        referral_code=order_data.referral_code,
    )

    created_orders: list[models.Order] = []
    pre_wallet_totals: dict[str, Decimal] = {}
    for split_index, source in enumerate(sources, start=1):
        rows = grouped[source]
        discount = discounts[source]
        shipping_fee = charged_shipping_fee if source == shipping_source else Decimal("0")
        requested_deposit_type = (
            order_data.deposit_type.value if order_data.deposit_type else None
        )
        plan = build_group_financial_plan(
            rows,
            discount=discount,
            shipping_fee=shipping_fee,
            requested_deposit_type=requested_deposit_type,
        )
        subtotal = plan["subtotal"]
        total = plan["total"]
        pre_wallet_totals[source] = total
        requires_deposit = plan["requires_deposit"]
        deposit_type = plan["deposit_type"]
        deposit = plan["deposit_amount"]

        notes = list(discount_notes)
        if len(sources) > 1:
            notes.append(
                f"Tách từ checkout {checkout_group_id}: "
                f"{'hàng Trung Quốc' if source == FULFILLMENT_CHINA else 'hàng Việt Nam'}"
            )
        order = crud.order.create_order_with_deposit(
            db=db,
            user_id=current_user.id if current_user else None,
            customer_name=order_data.customer_name,
            customer_phone=order_data.customer_phone,
            customer_email=order_data.customer_email,
            customer_address=order_data.customer_address,
            customer_note=order_data.customer_note,
            payment_method=(
                PaymentMethodEnum.BANK_TRANSFER.value
                if requires_deposit
                else PaymentMethodEnum.COD.value
            ),
            shipping_method=order_data.shipping_method,
            subtotal=subtotal,
            discount_amount=discount,
            shipping_fee=shipping_fee,
            total_amount=total,
            admin_notes="\n".join(notes),
            requires_deposit=requires_deposit,
            deposit_type=deposit_type,
            deposit_percentage=plan["deposit_percentage"],
            deposit_amount=deposit,
            remaining_amount=plan["remaining_amount"],
            items=rows,
            referrer_user_id=referrer_user_id,
            fulfillment_source=source,
            checkout_group_id=checkout_group_id,
            split_index=split_index,
            stock_hold_expires_at=(
                datetime.now() + timedelta(hours=settings.VN_STOCK_HOLD_HOURS)
                if source == FULFILLMENT_VIETNAM and requires_deposit
                else None
            ),
            commit=False,
        )
        created_orders.append(order)

    primary_order = next(
        (row for row in created_orders if _dec(row.discount_amount) > 0),
        created_orders[0],
    )
    if current_user is not None and applied_promotion and welcome_discount > 0:
        grant_svc.mark_grant_used(
            db,
            user_id=current_user.id,
            promotion_id=applied_promotion.id,
            order_id=primary_order.id,
        )
        crud_promotion.record_promotion_usage(
            db,
            promotion=applied_promotion,
            user_id=current_user.id,
            order_id=primary_order.id,
            discount_amount=welcome_discount,
            grant_id=applied_grant_id,
        )

    requested_wallet = (
        _dec(order_data.wallet_amount)
        if current_user is not None and order_data.wallet_amount
        else Decimal("0")
    )
    wallet_allocations = {source: Decimal("0") for source in sources}
    if requested_wallet > 0 and current_user is not None:
        wallet = affiliate_svc.get_or_create_wallet(db, current_user.id)
        wallet_total = min(requested_wallet, _dec(wallet.balance))
        wallet_allocations = allocate_group_wallet(wallet_total, pre_wallet_totals, sources)

    for order in created_orders:
        source = order.fulfillment_source
        allocated_wallet = wallet_allocations.get(source, Decimal("0"))
        if allocated_wallet > 0 and current_user is not None:
            used = affiliate_svc.apply_wallet_to_order(
                db, current_user.id, order, allocated_wallet
            )
            if used != allocated_wallet:
                raise HTTPException(
                    status_code=409,
                    detail="Số dư ví thay đổi trong lúc đặt hàng. Vui lòng thử lại.",
                )
            note = f"Thanh toán ví: -{used:,.0f} đ"
            order.admin_notes = "\n".join(
                [part for part in [order.admin_notes, note] if part]
            )
        if not order.requires_deposit:
            affiliate_svc.create_pending_commission_for_order(db, order)
        if shipment_svc.should_have_timeline(order):
            shipment_svc.ensure_shipment_timeline(db, order)

    db.flush()
    for order in created_orders:
        loaded = reload_order_with_items(db, order.id)
        if loaded:
            try:
                reserve_warehouse_stock_for_order(db, loaded)
            except WarehouseStockError as exc:
                raise HTTPException(status_code=400, detail=exc.message) from exc

    db.commit()
    for order in created_orders:
        db.refresh(order)
        if referrer_user_id:
            background_tasks.add_task(
                affiliate_svc.notify_referrer_new_order_task, order.id
            )
        if order.customer_email or (
            getattr(current_user, "email", None) if current_user else None
        ):
            background_tasks.add_task(send_order_created_email_task, order.id)

    next_action = next(
        (order.id for order in created_orders if order.requires_deposit),
        created_orders[0].id,
    )
    return {
        "orders": [_serialize_order(db, order) for order in created_orders],
        "checkout_group_id": checkout_group_id,
        "charged_shipping_fee": charged_shipping_fee,
        "next_action_order_id": next_action,
    }

