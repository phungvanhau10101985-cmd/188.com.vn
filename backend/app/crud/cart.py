# backend/app/crud/cart.py - COMPLETE FIXED VERSION
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models.cart import CartItem, Cart
from app.models.product import Product
from app.schemas.cart import CartItemCreate, CartItemUpdate

class CartItemCRUD:
    """CRUD operations for CartItem"""
    
    def get_or_create_cart(self, db: Session, user_id: int) -> Cart:
        """Đảm bảo user có cart record"""
        cart = db.query(Cart).filter(Cart.user_id == user_id).first()
        if not cart:
            cart = Cart(user_id=user_id)
            db.add(cart)
            db.commit()
            db.refresh(cart)
        return cart
    
    def get_cart_item(self, db: Session, cart_item_id: int) -> Optional[CartItem]:
        return db.query(CartItem).filter(CartItem.id == cart_item_id).first()
    
    def get_user_cart_items(self, db: Session, user_id: int) -> List[CartItem]:
        return db.query(CartItem).filter(CartItem.user_id == user_id).all()
    
    def create_cart_item(self, db: Session, user_id: int, cart_item: CartItemCreate) -> CartItem:
        # 1. Đảm bảo user có cart record
        cart = self.get_or_create_cart(db, user_id)
        
        # 2. Get product info
        product = db.query(Product).filter(Product.id == cart_item.product_id).first()
        if not product:
            raise ValueError(f"Product {cart_item.product_id} not found")
        
        # 3. Check if item already exists in cart
        existing = db.query(CartItem).filter(
            CartItem.cart_id == cart.id,
            CartItem.product_id == cart_item.product_id,
            CartItem.selected_size == cart_item.selected_size,
            CartItem.selected_color == cart_item.selected_color
        ).first()
        
        if existing:
            # Update quantity
            existing.quantity += cart_item.quantity
            existing.selected_color_name = cart_item.selected_color_name
            existing.total_price = existing.unit_price * existing.quantity
            existing.updated_at = datetime.now()
            db.commit()
            db.refresh(existing)
            return existing
        
        # 4. Create new cart item với đầy đủ cột database yêu cầu
        unit_price = product.price
        total_price = unit_price * cart_item.quantity
        
        # Tạo product_data từ product
        product_data = {
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "main_image": product.main_image,
            "slug": product.slug,
            "category_id": product.category_id,
            "deposit_require": product.deposit_require
        }
        
        now = datetime.now()
        db_cart_item = CartItem(
            cart_id=cart.id,  # QUAN TRỌNG: phải có cart_id (notnull)
            user_id=user_id,
            product_id=cart_item.product_id,
            product_data=product_data,  # QUAN TRỌNG: phải có product_data (notnull)
            quantity=cart_item.quantity,
            selected_size=cart_item.selected_size,
            selected_color=cart_item.selected_color,
            selected_color_name=cart_item.selected_color_name,
            unit_price=unit_price,  # QUAN TRỌNG: phải có unit_price (notnull)
            total_price=total_price,  # QUAN TRỌNG: phải có total_price (notnull)
            product_name=product.name,
            product_price=product.price,
            product_image=product.main_image,
            requires_deposit=product.deposit_require,
            created_at=now,  # Đảm bảo có giá trị, tránh Pydantic datetime_type lỗi
        )
        
        db.add(db_cart_item)
        db.commit()
        db.refresh(db_cart_item)
        return db_cart_item
    
    def update_cart_item(self, db: Session, cart_item_id: int, cart_item_update: CartItemUpdate) -> Optional[CartItem]:
        db_cart_item = db.query(CartItem).filter(CartItem.id == cart_item_id).first()
        if db_cart_item:
            update_data = cart_item_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_cart_item, field, value)
            
            # Update total_price nếu quantity thay đổi
            if 'quantity' in update_data:
                db_cart_item.total_price = db_cart_item.unit_price * db_cart_item.quantity
            
            db_cart_item.updated_at = datetime.now()
            db.commit()
            db.refresh(db_cart_item)
        return db_cart_item
    
    def delete_cart_item(self, db: Session, cart_item_id: int) -> Optional[CartItem]:
        db_cart_item = db.query(CartItem).filter(CartItem.id == cart_item_id).first()
        if db_cart_item:
            db.delete(db_cart_item)
            db.commit()
        return db_cart_item
    
    def clear_user_cart(self, db: Session, user_id: int) -> int:
        """Clear all cart items for user"""
        # Lấy cart của user
        cart = db.query(Cart).filter(Cart.user_id == user_id).first()
        if not cart:
            return 0
        
        result = db.query(CartItem).filter(CartItem.cart_id == cart.id).delete()
        db.commit()
        return result
    
    def get_cart_summary(self, db: Session, user_id: int) -> dict:
        """Get cart summary (total items, total price)"""
        items = self.get_user_cart_items(db, user_id)
        
        total_items = sum(item.quantity for item in items)
        total_price = sum(item.total_price for item in items)  # Dùng total_price từ database
        
        return {
            "total_items": total_items,
            "total_price": total_price,
            "items_count": len(items),
            "requires_deposit": any(item.requires_deposit for item in items if item.requires_deposit is not None)
        }
    
    def get_cart_item_count(self, db: Session, user_id: int) -> int:
        """Get total number of items in cart (sum of quantities)"""
        items = self.get_user_cart_items(db, user_id)
        return sum(item.quantity for item in items)
    
    def migrate_guest_cart(self, db: Session, user_id: int, guest_items: list) -> dict:
        """Migrate guest cart items to user cart"""
        # Đảm bảo user có cart
        cart = self.get_or_create_cart(db, user_id)
        
        migrated_count = 0
        
        for guest_item in guest_items:
            try:
                cart_item_data = CartItemCreate(
                    product_id=guest_item.product_id,
                    quantity=guest_item.quantity,
                    selected_size=guest_item.selected_size,
                    selected_color=guest_item.selected_color,
                    selected_color_name=guest_item.selected_color_name
                )
                self.create_cart_item(db, user_id, cart_item_data)
                migrated_count += 1
            except Exception as e:
                # Skip items that can't be migrated
                print(f"Failed to migrate item: {e}")
                continue
        
        # Get updated cart
        items = self.get_user_cart_items(db, user_id)
        summary = self.get_cart_summary(db, user_id)
        
        return {
            "message": f"Migrated {migrated_count} items",
            "migrated_items": migrated_count,
            "total_items": summary["total_items"],
            "cart": {
                "id": cart.id,
                "user_id": user_id,
                "items": items,
                "created_at": cart.created_at,
                "updated_at": cart.updated_at,
                **summary
            }
        }

cart = CartItemCRUD()