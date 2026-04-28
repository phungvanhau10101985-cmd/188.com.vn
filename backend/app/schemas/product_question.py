# backend/app/schemas/product_question.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProductQuestionBase(BaseModel):
    user_name: str = Field("", description="Tên người hỏi")
    content: str = Field("", description="Nội dung câu hỏi")
    group: int = Field(0, description="Nhóm câu hỏi (khớp product.group_question)")
    product_id: Optional[int] = Field(None, description="ID sản phẩm (null = theo nhóm)")
    useful: int = Field(0, description="Số lượt bình chọn hữu ích")
    reply_admin_name: str = Field("", description="Tên admin trả lời")
    reply_admin_content: str = Field("", description="Nội dung admin trả lời")
    reply_user_one_name: str = Field("", description="Tên user 1 trả lời")
    reply_user_one_content: str = Field("", description="Nội dung user 1 trả lời")
    reply_user_two_name: str = Field("", description="Tên user 2 trả lời")
    reply_user_two_content: str = Field("", description="Nội dung user 2 trả lời")
    reply_count: int = Field(0, description="Số câu trả lời (2 = khóa)")
    is_active: bool = Field(True, description="Kích hoạt")


class ProductQuestionCreate(ProductQuestionBase):
    created_at: Optional[datetime] = None  # Import Excel: thời gian ngẫu nhiên 1–10 ngày trước
    is_imported: bool = False


class ProductQuestionUpdate(BaseModel):
    user_name: Optional[str] = None
    content: Optional[str] = None
    group: Optional[int] = None
    product_id: Optional[int] = None
    useful: Optional[int] = None
    reply_admin_name: Optional[str] = None
    reply_admin_content: Optional[str] = None
    reply_admin_at: Optional[datetime] = None
    reply_user_one_id: Optional[int] = None
    reply_user_one_name: Optional[str] = None
    reply_user_one_content: Optional[str] = None
    reply_user_one_at: Optional[datetime] = None
    reply_user_two_id: Optional[int] = None
    reply_user_two_name: Optional[str] = None
    reply_user_two_content: Optional[str] = None
    reply_user_two_at: Optional[datetime] = None
    reply_count: Optional[int] = None
    is_active: Optional[bool] = None


class ProductQuestionResponse(ProductQuestionBase):
    id: int
    reply_admin_at: Optional[datetime] = None
    reply_user_one_id: Optional[int] = None
    reply_user_one_at: Optional[datetime] = None
    reply_user_two_id: Optional[int] = None
    reply_user_two_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_imported: bool = False
    display_created_at: Optional[datetime] = None  # Khi is_imported: thời gian ngẫu nhiên 1-20 ngày trước
    product_slug: Optional[str] = None  # Slug sản phẩm (khi product_id có) để link "Xem câu hỏi"
    user_has_voted: Optional[bool] = None  # True nếu user hiện tại đã bấm hữu ích (chỉ khi có auth)

    class Config:
        from_attributes = True


class UsefulToggleResponse(BaseModel):
    """Response sau khi bấm/bỏ bấm nút Hữu ích."""
    useful: int = Field(..., description="Số lượt hữu ích sau khi toggle")
    user_has_voted: bool = Field(..., description="User hiện tại đang vote (đã bấm hữu ích)")


class ProductQuestionListResponse(BaseModel):
    items: List[ProductQuestionResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 10


class ProductQuestionAskCreate(BaseModel):
    """Khách đặt câu hỏi (cần đăng nhập)"""
    product_id: int = Field(..., description="ID sản phẩm (database id)")
    content: str = Field(..., min_length=1, description="Nội dung câu hỏi")


class ProductQuestionReplyCreate(BaseModel):
    """Người đã mua hàng trả lời câu hỏi"""
    content: str = Field(..., min_length=1, description="Nội dung trả lời")
