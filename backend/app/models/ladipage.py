# backend/app/models/ladipage.py - Ladipage AI (landing page bán hàng tạo bởi Gemini)
"""
Ladipage: landing page bán hàng độc lập (URL `/lp/<slug>`), tạo theo danh mục cấp 3 hoặc theo
sản phẩm admin chọn. Nội dung/ảnh do Gemini sinh ra lưu trong `LadipageSection.data` (JSON).

QUAN TRỌNG: AI KHÔNG BAO GIỜ ghi ngược vào bảng `products`. Danh sách sản phẩm hiển thị luôn
được resolve "live" từ `category_id`/`product_ids` tại thời điểm render — không lưu bản sao
tên/giá/ảnh sản phẩm trong ladipage.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class Ladipage(Base):
    __tablename__ = "ladipages"

    id = Column(Integer, primary_key=True, index=True)

    slug = Column(String(300), unique=True, index=True, nullable=False)
    title = Column(String(500), nullable=False)
    # draft | published
    status = Column(String(20), default="draft", nullable=False, index=True)

    # category | products
    source_type = Column(String(20), nullable=False)
    category_id = Column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # list[int] products.id — chỉ dùng khi source_type = "products"
    product_ids = Column(JSON, default=list)

    admin_brief = Column(Text, nullable=True)
    include_material = Column(Boolean, default=True, nullable=False)
    include_faq = Column(Boolean, default=True, nullable=False)
    # Số sản phẩm hiển thị tối đa khi nguồn = danh mục (top bán chạy)
    products_limit = Column(Integer, default=12, nullable=False)
    # Ladipage danh mục: chỉ resolve SP cùng chất liệu (trim + không phân biệt hoa thường)
    material_filter = Column(String(100), nullable=True)

    meta_title = Column(String(500), nullable=True)
    meta_description = Column(String(1000), nullable=True)

    created_by = Column(
        Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    published_at = Column(DateTime(timezone=True), nullable=True)

    category_rel = relationship("Category", foreign_keys=[category_id])
    sections = relationship(
        "LadipageSection",
        back_populates="ladipage",
        cascade="all, delete-orphan",
        order_by="LadipageSection.order_index",
    )

    def __repr__(self):
        return f"<Ladipage {self.slug} ({self.status})>"


class LadipageSection(Base):
    __tablename__ = "ladipage_sections"

    id = Column(Integer, primary_key=True, index=True)
    ladipage_id = Column(
        Integer, ForeignKey("ladipages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # hero | highlights | material | products_grid | trust_cta | faq
    section_type = Column(String(30), nullable=False)
    order_index = Column(Integer, default=0, nullable=False)
    # pending | generating | ready | error
    status = Column(String(20), default="pending", nullable=False)
    data = Column(JSON, default=dict)
    # Prompt ảnh gần nhất dùng để sinh (cho phép sửa lại rồi tạo lại đúng chỗ)
    prompt_used = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    ladipage = relationship("Ladipage", back_populates="sections")

    def __repr__(self):
        return f"<LadipageSection {self.section_type} of ladipage={self.ladipage_id}>"
