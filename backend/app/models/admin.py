# backend/app/models/admin.py - BASIC ADMIN MODEL
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Text, ForeignKey, JSON
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

    # Khách có quyền quản trị: phiên đăng nhập khách → đổi lấy JWT admin (không dùng mật khẩu admin riêng).
    linked_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)

    # Quyền từng mục (danh sách chuỗi — xem ALLOWED_MODULE_KEYS). null = chỉ dùng preset theo role.
    granular_permissions = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # ========== RELATIONSHIPS ==========
    linked_user = relationship("User", foreign_keys=[linked_user_id])
    orders_managed = relationship("Order", back_populates="admin_manager", cascade="all, delete-orphan")
    payments_confirmed = relationship("Payment", back_populates="admin_confirmer", cascade="all, delete-orphan")
    # ===================================
    
    def __repr__(self):
        return f"<AdminUser {self.username}>"


class AdminStaffRolePreset(Base):
    """Preset mục menu + CRUD mặc định cho NV (order/product/content manager). Super_admin chỉnh qua API."""

    __tablename__ = "admin_staff_role_presets"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(32), unique=True, nullable=False, index=True)
    modules = Column(JSON, nullable=False)
    module_crud = Column(JSON, nullable=False)