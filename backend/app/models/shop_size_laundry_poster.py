"""Ảnh size + giặt tẩy đã dịch, dùng lại theo shop Trung Quốc và danh mục cấp 2."""

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


class ShopCat2SizeLaundryPoster(Base):
    __tablename__ = "shop_cat2_size_laundry_posters"
    __table_args__ = (
        UniqueConstraint(
            "shop_name_chinese_norm",
            "category_level2_slug",
            name="uq_shop_cat2_size_laundry_poster",
        ),
    )

    id = Column(Integer, primary_key=True)
    shop_name_chinese_norm = Column(String(200), nullable=False, index=True)
    category_level2_slug = Column(String(300), nullable=False, index=True)
    image_url = Column(String(800), nullable=False)
    size_image_url = Column(String(800), nullable=True)
    laundry_image_url = Column(String(800), nullable=True)
    render_version = Column(String(40), nullable=True)
    source_product_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
