# backend/app/api/endpoints/cart.py - COMPLETE FIXED VERSION
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.crud.cart import cart as cart_crud, _resolve_cart_line_image
import app.schemas as schemas
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse, CartItemResponse
from app.models.cart import CartItem, Cart
from app.services.birthday_discount import get_birthday_discount_for_user
from app.services.cart_discounts import build_cart_discount_fields

router = APIRouter()


def _is_warehouse_cart_line(item: CartItem) -> bool:
    from app.services.warehouse_clearance import is_warehouse_cart_product

    pd = item.product_data if isinstance(item.product_data, dict) else {}
    return is_warehouse_cart_product(item.product, pd)


def _cart_line_list_price(item: CartItem, *, is_wh: bool = False, db: Optional[Session] = None) -> float:
    """Giá gốc catalog (list) — dòng kho: ưu tiên giá SP gốc trên shop."""
    pd = item.product_data if isinstance(item.product_data, dict) else {}
    if is_wh and item.product is not None and db is not None:
        from app.services.warehouse_clearance import resolve_warehouse_list_price

        return resolve_warehouse_list_price(db, item.product)
    if is_wh and item.product is not None:
        return float(item.product.price or 0)
    if pd.get("list_price") is not None:
        try:
            lp = float(pd["list_price"])
            if lp > 0:
                return lp
        except (TypeError, ValueError):
            pass
    if item.product is not None:
        return float(item.product.price or 0)
    if pd.get("original_price") is not None:
        try:
            return float(pd["original_price"])
        except (TypeError, ValueError):
            pass
    return float(item.product_price or 0)


def _cart_items_with_site_sale_pricing(
    db: Session,
    user: User,
    items: List[CartItem],
) -> tuple[List[CartItemResponse], float, dict]:
    from app.services.sale_calendar import apply_site_sale_to_price, resolve_sale_calendar_state
    from app.services import warehouse_clearance as wh_clearance_svc
    from app.services.google_automated_discount import read_google_discount_lock

    sale_state = resolve_sale_calendar_state(db, user=user)
    wh_enabled, wh_pct = wh_clearance_svc.get_warehouse_clearance_settings(db)
    total_price = 0.0
    cart_items_response: List[CartItemResponse] = []
    for item in items:
        resp = _cart_item_to_response(item)
        is_wh = _is_warehouse_cart_line(item)
        base = _cart_line_list_price(item, is_wh=is_wh, db=db)
        sellable: Optional[int] = None
        pd_raw = dict(resp.product_data or {})
        google_lock = read_google_discount_lock(pd_raw) if not is_wh else None
        if is_wh:
            from app.services.warehouse_stock import warehouse_sellable_qty

            pricing = wh_clearance_svc.apply_clearance_pricing(base, percent=wh_pct)
            line_unit = float(pricing["display_price"])
            resp.product_price = line_unit
            resp.list_price = base if base > 0 else None
            resp.original_price = base if base > line_unit else None
            resp.site_sale = None
            if item.product is not None:
                sellable = warehouse_sellable_qty(item.product)
        elif google_lock:
            line_unit = float(google_lock["price"])
            list_for_compare = float(google_lock.get("prior_price") or base or line_unit)
            resp.product_price = line_unit
            resp.list_price = list_for_compare if list_for_compare > 0 else None
            resp.original_price = list_for_compare if list_for_compare > line_unit else None
            resp.site_sale = None
        else:
            pricing = apply_site_sale_to_price(base, sale_state)
            line_unit = float(pricing["display_price"])
            resp.product_price = line_unit
            resp.list_price = base if base > 0 else None
            if sale_state.is_active and pricing.get("savings_amount", 0) > 0:
                resp.original_price = base
            resp.site_sale = {
                **pricing,
                "event_label": sale_state.event_label,
                "event_date": sale_state.event_date.isoformat() if sale_state.event_date else None,
                "countdown_to": sale_state.countdown_to.isoformat() if sale_state.countdown_to else None,
            }
        pd = dict(resp.product_data or {})
        if google_lock:
            pd["price"] = line_unit
            pd["list_price"] = float(google_lock.get("prior_price") or base or line_unit)
            if pd["list_price"] > line_unit:
                pd["original_price"] = pd["list_price"]
            pd["google_automated_discount"] = pd_raw.get("google_automated_discount")
        else:
            pd["list_price"] = base
            pd["price"] = line_unit
        if is_wh:
            pd["is_warehouse_clearance"] = True
            pd["warehouse_clearance_percent"] = wh_pct
            pd["original_price"] = base
            if item.product is not None:
                pd["available"] = int(sellable if sellable is not None else item.product.available or 0)
                pd["warehouse_available"] = int(item.product.available or 0)
                if not str(pd.get("product_id") or "").strip():
                    pd["product_id"] = item.product.product_id
                wh_clearance_svc.apply_warehouse_cart_product_data_slug(db, item.product, pd)
        resp.product_data = pd
        total_price += line_unit * int(item.quantity or 0)
        cart_items_response.append(resp)
    return cart_items_response, total_price, sale_state.to_public_dict()


def _single_cart_item_response(db: Session, user: User, item: CartItem) -> CartItemResponse:
    responses, _, _ = _cart_items_with_site_sale_pricing(db, user, [item])
    return responses[0]


def _cart_item_to_response(item: CartItem) -> CartItemResponse:
    pd_raw = getattr(item, "product_data", None)
    pd = dict(pd_raw) if isinstance(pd_raw, dict) else {}
    line_image = (item.product_image or "").strip() or (pd.get("main_image") or "").strip()
    if not line_image and item.product is not None:
        line_image = _resolve_cart_line_image(
            item.product,
            item.selected_color,
            pd,
            None,
        )
    if line_image:
        pd = {**pd, "main_image": line_image}
    return CartItemResponse(
        id=item.id,
        cart_id=item.cart_id,
        user_id=item.user_id,
        product_id=item.product_id,
        product_code=item.product.product_id if item.product else None,
        quantity=item.quantity,
        selected_size=item.selected_size,
        selected_color=item.selected_color,
        selected_color_name=item.selected_color_name,
        product_name=item.product_name or "",
        product_price=float(item.product_price) if item.product_price is not None else 0.0,
        product_image=line_image or item.product_image,
        product_data=pd or None,
        requires_deposit=bool(item.requires_deposit) if item.requires_deposit is not None else False,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=CartResponse, include_in_schema=False)
@router.get("/", response_model=CartResponse)
def get_user_cart(
    promo_code: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's cart items"""
    # Lấy hoặc tạo cart
    cart_record = db.query(Cart).filter(Cart.user_id == current_user.id).first()
    if not cart_record:
        cart_record = Cart(user_id=current_user.id)
        db.add(cart_record)
        db.commit()
        db.refresh(cart_record)
    
    items = cart_crud.get_user_cart_items(db, user_id=current_user.id)

    cart_items_response, total_price, site_sale_state = _cart_items_with_site_sale_pricing(
        db, current_user, items
    )
    list_total = sum(
        _cart_line_list_price(item, db=db) * int(item.quantity or 0) for item in items
    )
    summary = cart_crud.get_cart_summary(db, user_id=current_user.id)
    birthday_discount = get_birthday_discount_for_user(db, current_user)
    discount_fields = build_cart_discount_fields(
        db,
        user=current_user,
        total_price=total_price,
        list_subtotal=list_total,
        promo_code=promo_code,
    )

    return CartResponse(
        id=cart_record.id,
        user_id=current_user.id,
        items=cart_items_response,
        total_items=summary["total_items"],
        total_price=total_price,
        items_count=summary["items_count"],
        requires_deposit=summary["requires_deposit"],
        created_at=cart_record.created_at,
        updated_at=cart_record.updated_at,
        birthday_next_date=birthday_discount.next_birthday.isoformat() if birthday_discount.next_birthday else None,
        site_sale=site_sale_state,
        **discount_fields,
    )

@router.post("/items", response_model=CartItemResponse)
def add_item_to_cart(
    cart_item: CartItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add item to cart"""
    try:
        created_item = cart_crud.create_cart_item(db, user_id=current_user.id, cart_item=cart_item)
        created_item = cart_crud.get_cart_item(db, cart_item_id=created_item.id)
        if not created_item:
            raise HTTPException(status_code=500, detail="Không tải được dòng giỏ hàng vừa thêm.")
        return _single_cart_item_response(db, current_user, created_item)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại. Kiểm tra lại product_id (dùng id số của sản phẩm).")
        if "kho" in msg.lower() or "hết hàng" in msg.lower() or "tối đa" in msg.lower():
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=404, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@router.put("/items/{item_id}", response_model=CartItemResponse)
def update_cart_item(
    item_id: int,
    cart_item_update: CartItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update cart item quantity"""
    # Verify ownership
    cart_item = cart_crud.get_cart_item(db, cart_item_id=item_id)
    if not cart_item or cart_item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    try:
        updated_item = cart_crud.update_cart_item(db, cart_item_id=item_id, cart_item_update=cart_item_update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    updated_item = cart_crud.get_cart_item(db, cart_item_id=item_id)
    if not updated_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    return _single_cart_item_response(db, current_user, updated_item)

@router.delete("/items/{item_id}")
def remove_item_from_cart(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Remove item from cart"""
    # Verify ownership
    cart_item = cart_crud.get_cart_item(db, cart_item_id=item_id)
    if not cart_item or cart_item.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    deleted_item = cart_crud.delete_cart_item(db, cart_item_id=item_id)
    if not deleted_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    return {"message": "Item removed from cart", "item_id": item_id}

@router.post("/migrate-guest", response_model=schemas.CartMergeResponse)
def migrate_guest_cart(
    guest_cart: schemas.GuestCartMigration,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Migrate guest cart items to user cart"""
    try:
        result = cart_crud.migrate_guest_cart(
            db, 
            user_id=current_user.id, 
            guest_items=guest_cart.guest_items
        )
        
        # Get cart record
        cart_record = db.query(Cart).filter(Cart.user_id == current_user.id).first()
        if not cart_record:
            cart_record = Cart(user_id=current_user.id)
            db.add(cart_record)
            db.commit()
            db.refresh(cart_record)
        
        # Get cart items for response
        items = cart_crud.get_user_cart_items(db, user_id=current_user.id)

        cart_items_response, total_price, site_sale_state = _cart_items_with_site_sale_pricing(
            db, current_user, items
        )
        list_total = sum(
            _cart_line_list_price(item, db=db) * int(item.quantity or 0) for item in items
        )
        summary = cart_crud.get_cart_summary(db, user_id=current_user.id)

        birthday_discount = get_birthday_discount_for_user(db, current_user)
        discount_fields = build_cart_discount_fields(
            db,
            user=current_user,
            total_price=total_price,
            list_subtotal=list_total,
        )

        return schemas.CartMergeResponse(
            message=result.get("message", "Migration completed"),
            migrated_items=result.get("migrated_items", 0),
            total_items=result.get("total_items", 0),
            cart=CartResponse(
                id=cart_record.id,
                user_id=current_user.id,
                items=cart_items_response,
                total_items=summary["total_items"],
                total_price=total_price,
                items_count=summary["items_count"],
                requires_deposit=summary["requires_deposit"],
                created_at=cart_record.created_at,
                updated_at=cart_record.updated_at,
                birthday_next_date=birthday_discount.next_birthday.isoformat() if birthday_discount.next_birthday else None,
                site_sale=site_sale_state,
                **discount_fields,
            )
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@router.get("/count", response_model=dict)
def get_cart_item_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get cart item count"""
    items = cart_crud.get_user_cart_items(db, user_id=current_user.id)
    count = len(items)
    return {"count": count}

@router.delete("", response_model=dict, include_in_schema=False)
@router.delete("/", response_model=dict)
def clear_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Clear user's cart"""
    count = cart_crud.clear_user_cart(db, user_id=current_user.id)
    return {"message": f"Cleared {count} items from cart", "cleared_count": count}
