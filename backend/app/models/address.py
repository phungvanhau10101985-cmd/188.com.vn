# backend/app/models/address.py - Sổ địa chỉ khách hàng
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


class UserAddress(Base):
    __tablename__ = "user_addresses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Thông tin giao hàng
    full_name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)

    # Địa chỉ: Tỉnh/TP, Quận/Huyện, Phường/Xã, Địa chỉ cụ thể
    province = Column(String(255), nullable=True)   # Tỉnh/Thành phố
    district = Column(String(255), nullable=True)    # Quận/Huyện
    ward = Column(String(255), nullable=True)        # Phường/Xã
    street_address = Column(Text, nullable=False)  # Số nhà, đường, thôn xóm

    is_default = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="addresses")

    def __repr__(self):
        return f"<UserAddress {self.id} user={self.user_id}>"
