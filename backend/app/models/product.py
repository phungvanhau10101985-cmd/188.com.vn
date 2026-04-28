# backend/app/models/product.py - PRODUCTION READY
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class Product(Base):
    __tablename__ = "products"
    
    # SYSTEM FIELDS
    id = Column(Integer, primary_key=True, index=True)
    
    # ========== EXCEL COLUMNS ==========
    product_id = Column(String(255), unique=True, index=True, nullable=False)
    code = Column(String(100), index=True)
    origin = Column(String(100))
    brand_name = Column(String(200))
    name = Column(String(500), nullable=False)
    description = Column(Text)  # Mô tả sản phẩm (cột F)
    price = Column(Float, default=0)
    shop_name = Column(String(200))
    shop_id = Column(String(100))
    pro_lower_price = Column(String(255))
    pro_high_price = Column(String(255))
    group_rating = Column(Integer, default=0)
    group_question = Column(Integer, default=0)
    sizes = Column(JSON, default=list)
    colors = Column(JSON, default=list)
    images = Column(JSON, default=list)  # Thư viện ảnh (cột P)
    gallery = Column(JSON, default=list)  # Ảnh chi tiết (cột Q)
    link_default = Column(String(500))
    video_link = Column(String(500))
    main_image = Column(String(500))
    likes = Column(Integer, default=0)
    purchases = Column(Integer, default=0)
    rating_total = Column(Integer, default=0)
    question_total = Column(Integer, default=0)
    rating_point = Column(Float, default=0.0)
    available = Column(Integer, default=0)
    deposit_require = Column(Boolean, default=False)  # Cột AA
    category = Column(String(100))  # Tên category (string từ Excel)
    subcategory = Column(String(100))
    sub_subcategory = Column(String(100))
    # Lưu danh mục gốc để có thể áp lại mapping khi xóa mapping
    raw_category = Column(String(100))
    raw_subcategory = Column(String(100))
    raw_sub_subcategory = Column(String(100))
    material = Column(String(100))
    style = Column(String(100))
    color = Column(String(100))
    occasion = Column(String(100))
    features = Column(JSON, default=list)
    weight = Column(String(100))
    # SEO fields
    meta_title = Column(String(500))
    meta_description = Column(String(1000))
    meta_keywords = Column(String(1000))
    # Cột AK: Thông tin sản phẩm (JSON: product_info, specifications, variants, target_audience, market_info)
    product_info = Column(JSON, nullable=True)
    
    # ========== ADDITIONAL FIELDS ==========
    slug = Column(String(500), unique=True, index=True)
    
    # ForeignKey đến Category (quan hệ database)
    category_id = Column(
        Integer, 
        ForeignKey("categories.id", ondelete="SET NULL"), 
        nullable=True,
        index=True
    )
    
    # SYSTEM FIELDS
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    # ========== RELATIONSHIP CHUẨN ==========
    # Một Product thuộc một Category
    category_rel = relationship(
        "Category", 
        back_populates="products",  # KHỚP với tên trong Category
        lazy="joined"  # Tự động join khi query
    )
    # ========================================
    
    # Các relationships khác
    order_items = relationship("OrderItem", back_populates="product", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Product({self.product_id}: {self.name[:30]}...)>"