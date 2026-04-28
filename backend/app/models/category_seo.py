# backend/app/models/category_seo.py - Model quản lý SEO danh mục
"""
Bảng lưu mapping canonical cho các danh mục trùng ý nghĩa.
Giúp tránh duplicate content và keyword cannibalization.
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, Float
from sqlalchemy.sql import func
from app.db.base import Base


class CategorySeoMapping(Base):
    """
    Mapping danh mục để SEO:
    - Xác định trang canonical cho các danh mục trùng ý nghĩa
    - Quyết định redirect hay noindex
    """
    __tablename__ = "category_seo_mappings"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Danh mục nguồn (slug)
    source_slug = Column(String(500), index=True, nullable=False)  # Có thể trùng slug nếu khác path
    source_name = Column(String(500), nullable=False)  # Tên hiển thị
    source_path = Column(String(1000), unique=True, index=True, nullable=False)  # Full path: unique key
    
    # Danh mục đích (canonical)
    canonical_slug = Column(String(500), index=True)  # NULL nếu tự nó là canonical
    canonical_name = Column(String(500))
    canonical_path = Column(String(1000))
    
    # Loại action
    action = Column(String(50), default="none")  # none, redirect, noindex, canonical_tag
    
    # AI analysis
    ai_confidence = Column(Float, default=0.0)  # Độ tin cậy của AI (0-1)
    ai_reason = Column(Text)  # Lý do AI đưa ra
    
    # Trạng thái
    status = Column(String(50), default="pending")  # pending, approved, rejected
    reviewed_by = Column(String(100))  # Admin đã review
    reviewed_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<CategorySeoMapping({self.source_slug} → {self.canonical_slug or 'CANONICAL'})>"


class CategorySeoDictionary(Base):
    """
    Từ điển các cụm từ đồng nghĩa trong danh mục.
    Giúp AI và rule-based phát hiện trùng ý nghĩa.
    VD: boot = giày boot, jacket = áo khoác
    """
    __tablename__ = "category_seo_dictionary"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Từ/cụm từ gốc
    term = Column(String(200), unique=True, index=True, nullable=False)
    
    # Các từ đồng nghĩa (JSON array hoặc comma-separated)
    synonyms = Column(Text, nullable=False)  # VD: "giày boot, boots, bốt"
    
    # Từ canonical (ưu tiên dùng)
    canonical_term = Column(String(200), nullable=False)  # VD: "giày boot"
    
    # Loại: category, material, style, color...
    term_type = Column(String(50), default="category")
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<CategorySeoDictionary({self.term} → {self.canonical_term})>"


class CategorySeoMeta(Base):
    """
    Lưu metadata SEO cố định theo từng danh mục (path):
    - 4 ảnh og:image (cố định, không query sản phẩm mỗi lần)
    - Mô tả SEO (viết một lần, dùng mãi)
    Mỗi lần mở danh mục chỉ cần đọc 1 row này thay vì query products.
    """
    __tablename__ = "category_seo_meta"

    id = Column(Integer, primary_key=True, index=True)
    category_path = Column(String(1000), unique=True, index=True, nullable=False)  # VD: giay-dep-nam/giay-luoi-nam

    # 4 ảnh cố định cho og:image (URL)
    image_1 = Column(String(2000))
    image_2 = Column(String(2000))
    image_3 = Column(String(2000))
    image_4 = Column(String(2000))

    # Mô tả SEO (150–160 ký tự), lưu một lần
    seo_description = Column(Text)

    # Đoạn văn SEO 150–300 từ (cuối trang danh mục), do AI viết
    seo_body = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CategorySeoMeta({self.category_path})>"
