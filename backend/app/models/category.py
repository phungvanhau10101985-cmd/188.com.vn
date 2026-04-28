# backend/app/models/category.py - PRODUCTION READY
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(300), unique=True, index=True)
    description = Column(Text)
    level = Column(Integer, default=1)
    image = Column(String(500))
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ========== RELATIONSHIP CHUẨN ==========
    # Một Category có nhiều Product
    products = relationship(
        "Product", 
        back_populates="category_rel",  # KHỚP với tên trong Product
        lazy="dynamic",  # Tối ưu performance
        cascade="all, delete-orphan",
        foreign_keys="[Product.category_id]"  # Chỉ định rõ foreign key
    )
    # ========================================

    def __repr__(self):
        return f"<Category {self.name}>"