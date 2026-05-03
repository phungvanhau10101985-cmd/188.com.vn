# backend/app/models/product_question.py - Câu hỏi Câu trả lời sản phẩm
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base import Base


class ProductQuestionUsefulVote(Base):
    """Bình chọn hữu ích: mỗi user chỉ bấm 1 lần mỗi câu hỏi (bấm lại = bỏ vote)."""
    __tablename__ = "product_question_useful_votes"
    __table_args__ = (UniqueConstraint("question_id", "user_id", name="uq_question_user"),)

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("product_questions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)


class ProductQuestion(Base):
    """
    Câu hỏi / câu trả lời sản phẩm.
    - Import từ Excel: group set, product_id NULL → hiển thị theo product.group_question.
    - Khách đặt câu hỏi: product_id set, group 0 → hiển thị theo id sản phẩm.
    """
    __tablename__ = "product_questions"

    id = Column(Integer, primary_key=True, index=True)
    # Người hỏi
    user_name = Column(String(255), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    # Nhóm câu hỏi (dùng cho câu hỏi import: khớp với product.group_question)
    group = Column(Integer, default=0)
    # ID sản phẩm (NULL = câu hỏi theo nhóm; set = câu hỏi của khách cho sản phẩm đó)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    # User đăng nhập đặt câu hỏi qua /ask (import Excel: NULL)
    ask_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    useful = Column(Integer, default=0)  # Số lượt bình chọn hữu ích

    # Admin trả lời
    reply_admin_name = Column(String(255), default="")
    reply_admin_content = Column(Text, default="")
    reply_admin_at = Column(DateTime(timezone=True), nullable=True)

    # User 1 trả lời
    reply_user_one_id = Column(Integer, nullable=True)  # ID user nếu có
    reply_user_one_name = Column(String(255), default="")
    reply_user_one_content = Column(Text, default="")
    reply_user_one_at = Column(DateTime(timezone=True), nullable=True)

    # User 2 trả lời
    reply_user_two_id = Column(Integer, nullable=True)
    reply_user_two_name = Column(String(255), default="")
    reply_user_two_content = Column(Text, default="")
    reply_user_two_at = Column(DateTime(timezone=True), nullable=True)

    # Số câu trả lời (2 = khóa, không cho trả lời nữa; 0 = còn cho trả lời)
    reply_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    # Import từ Excel: đánh dấu đã mua hàng từ 188, hiển thị thời gian ngẫu nhiên 1–10 ngày trước
    is_imported = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
