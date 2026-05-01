# backend/app/models/cart.py - COMPLETE FIXED VERSION (MATCH DATABASE)
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class Cart(Base):
    """Cart model với đầy đủ relationship"""
    __tablename__ = "carts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== RELATIONSHIPS ==========
    user = relationship("User", back_populates="cart")
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
    # ===================================
    
    def __repr__(self):
        return f"<Cart user_id={self.user_id}>"


class CartItem(Base):
    __tablename__ = "cart_items"
    
    # ========== CÁC CỘT THEO DATABASE THỰC TẾ ==========
    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("carts.id", ondelete="CASCADE"), nullable=False, index=True)  # notnull=1
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Các cột có trong database
    product_data = Column(JSON, nullable=False)  # notnull=1
    quantity = Column(Integer, default=1, nullable=False)
    selected_size = Column(String(50), nullable=True)
    selected_color = Column(String(200), nullable=True)
    unit_price = Column(Float, nullable=False)  # notnull=1
    total_price = Column(Float, nullable=False)  # notnull=1
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Các cột thêm sau
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    selected_color_name = Column(String(100), nullable=True)
    product_name = Column(String(500), nullable=True)
    product_price = Column(Float, nullable=True)
    product_image = Column(String(500), nullable=True)
    requires_deposit = Column(Boolean, default=False, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # ===================================================
    
    # Relationships
    user = relationship("User", back_populates="cart_items")
    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")
    
    def __repr__(self):
        return f"<CartItem {self.product_name} x{self.quantity}>"