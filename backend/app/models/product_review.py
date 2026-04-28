# backend/app/models/product_review.py - Đánh giá sản phẩm
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.sql import func
from app.db.base import Base


class ProductReviewUsefulVote(Base):
    """Bình chọn hữu ích đánh giá: mỗi user chỉ bấm 1 lần mỗi đánh giá."""
    __tablename__ = "product_review_useful_votes"
    __table_args__ = (UniqueConstraint("review_id", "user_id", name="uq_review_user"),)

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("product_reviews.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class ProductReview(Base):
    """
    Đánh giá sản phẩm.
    - Import từ Excel: group set, product_id NULL → hiển thị theo product.group_rating.
    - Khách đánh giá: product_id set (tương lai).
    - Chỉ admin được trả lời đánh giá (không có user reply).
    """
    __tablename__ = "product_reviews"

    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String(255), nullable=False, default="")
    star = Column(Integer, default=5)  # 1-5 sao
    title = Column(String(500), default="")
    content = Column(Text, nullable=False, default="")
    group = Column(Integer, default=0)  # Nhóm đánh giá (khớp product.group_rating)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)  # Khách đánh giá
    useful = Column(Integer, default=0)

    reply_name = Column(String(255), default="")  # Chỉ admin
    reply_content = Column(Text, default="")
    reply_at = Column(DateTime(timezone=True), nullable=True)

    images = Column(JSON, default=list)  # Danh sách URL ảnh
    is_active = Column(Boolean, default=True)
    is_imported = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
