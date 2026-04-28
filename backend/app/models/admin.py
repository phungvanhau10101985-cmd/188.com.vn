# backend/app/models/admin.py - BASIC ADMIN MODEL
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.db.base import Base

class AdminRole(enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    PRODUCT_MANAGER = "product_manager"
    ORDER_MANAGER = "order_manager"
    CONTENT_MANAGER = "content_manager"

class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    phone = Column(String(20))
    role = Column(Enum(AdminRole), default=AdminRole.ADMIN)
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== RELATIONSHIPS ==========
    orders_managed = relationship("Order", back_populates="admin_manager", cascade="all, delete-orphan")
    payments_confirmed = relationship("Payment", back_populates="admin_confirmer", cascade="all, delete-orphan")
    # ===================================
    
    def __repr__(self):
        return f"<AdminUser {self.username}>"