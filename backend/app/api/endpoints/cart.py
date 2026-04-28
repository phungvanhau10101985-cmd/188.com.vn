# backend/app/api/endpoints/cart.py - COMPLETE FIXED VERSION
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.crud.cart import cart as cart_crud
from app.crud import loyalty as crud_loyalty
import app.schemas as schemas
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartResponse, CartItemResponse
from app.models.cart import CartItem, Cart

router = APIRouter()

@router.get("", response_model=CartResponse, include_in_schema=False)
@router.get("/", response_model=CartResponse)
def get_user_cart(
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
    summary = cart_crud.get_cart_summary(db, user_id=current_user.id)
    
    # Calculate loyalty discount
    total_spent = crud_loyalty.calculate_user_spend_6_months(db, current_user.id)
    current_tier = crud_loyalty.get_tier_by_spend(db, total_spent)
    
    loyalty_discount_percent = 0.0
    loyalty_tier_name = None
    
    if current_tier:
        loyalty_discount_percent = current_tier.discount_percent
        loyalty_tier_name = current_tier.name
        
    total_price = float(summary["total_price"])
    loyalty_discount_amount = (total_price * loyalty_discount_percent) / 100
    final_price = total_price - loyalty_discount_amount
    
    # Convert CartItem models to CartItemResponse schema
    cart_items_response = []
    for item in items:
        cart_items_response.append(
            CartItemResponse(
                id=item.id,
                cart_id=item.cart_id,
                user_id=item.user_id,
                product_id=item.product_id,
                product_code=item.product.product_id if item.product else None,
                quantity=item.quantity,
                selected_size=item.selected_size,
                selected_color=item.selected_color,
                selected_color_name=item.selected_color_name,
                product_name=item.product_name,
                product_price=item.product_price,
                product_image=item.product_image,
                requires_deposit=item.requires_deposit,
                created_at=item.created_at,
                updated_at=item.updated_at
            )
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
        loyalty_discount_percent=loyalty_discount_percent,
        loyalty_discount_amount=loyalty_discount_amount,
        final_price=final_price,
        loyalty_tier_name=loyalty_tier_name
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
        
        # Convert to response schema
        return CartItemResponse(
            id=created_item.id,
            cart_id=created_item.cart_id,
            user_id=created_item.user_id,
            product_id=created_item.product_id,
            product_code=created_item.product.product_id if created_item.product else None,
            quantity=created_item.quantity,
            selected_size=created_item.selected_size,
            selected_color=created_item.selected_color,
            selected_color_name=created_item.selected_color_name,
            product_name=created_item.product_name,
            product_price=created_item.product_price,
            product_image=created_item.product_image,
            requires_deposit=created_item.requires_deposit,
            created_at=created_item.created_at,
            updated_at=created_item.updated_at
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail="Sản phẩm không tồn tại. Kiểm tra lại product_id (dùng id số của sản phẩm).")
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
    
    updated_item = cart_crud.update_cart_item(db, cart_item_id=item_id, cart_item_update=cart_item_update)
    if not updated_item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    
    return CartItemResponse(
        id=updated_item.id,
        cart_id=updated_item.cart_id,
        user_id=updated_item.user_id,
        product_id=updated_item.product_id,
        product_code=updated_item.product.product_id if updated_item.product else None,
        quantity=updated_item.quantity,
        selected_size=updated_item.selected_size,
        selected_color=updated_item.selected_color,
        selected_color_name=updated_item.selected_color_name,
        product_name=updated_item.product_name,
        product_price=updated_item.product_price,
        product_image=updated_item.product_image,
        requires_deposit=updated_item.requires_deposit,
        created_at=updated_item.created_at,
        updated_at=updated_item.updated_at
    )

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
        
        # Convert items to response format
        cart_items_response = []
        for item in items:
            cart_items_response.append(
                CartItemResponse(
                    id=item.id,
                    cart_id=item.cart_id,
                    user_id=item.user_id,
                    product_id=item.product_id,
                    product_code=item.product.product_id if item.product else None,
                    quantity=item.quantity,
                    selected_size=item.selected_size,
                    selected_color=item.selected_color,
                    selected_color_name=item.selected_color_name,
                    product_name=item.product_name,
                    product_price=item.product_price,
                    product_image=item.product_image,
                    requires_deposit=item.requires_deposit,
                    created_at=item.created_at,
                    updated_at=item.updated_at
                )
            )
        
        summary = cart_crud.get_cart_summary(db, user_id=current_user.id)
        
        # Calculate loyalty discount
        total_spent = crud_loyalty.calculate_user_spend_6_months(db, current_user.id)
        current_tier = crud_loyalty.get_tier_by_spend(db, total_spent)
        
        loyalty_discount_percent = 0.0
        loyalty_tier_name = None
        
        if current_tier:
            loyalty_discount_percent = current_tier.discount_percent
            loyalty_tier_name = current_tier.name
            
        total_price = float(summary["total_price"])
        loyalty_discount_amount = (total_price * loyalty_discount_percent) / 100
        final_price = total_price - loyalty_discount_amount
        
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
                loyalty_discount_percent=loyalty_discount_percent,
                loyalty_discount_amount=loyalty_discount_amount,
                final_price=final_price,
                loyalty_tier_name=loyalty_tier_name
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
