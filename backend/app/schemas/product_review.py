from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProductReviewBase(BaseModel):
    user_name: str = Field("", description="Tên người đánh giá")
    star: int = Field(5, ge=1, le=5, description="Số sao 1-5")
    title: str = Field("", description="Tiêu đề")
    content: str = Field("", description="Nội dung đánh giá")
    group: int = Field(0, description="Nhóm đánh giá (khớp product.group_rating)")
    product_id: Optional[int] = Field(None, description="ID sản phẩm (null = theo nhóm)")
    useful: int = Field(0, description="Số lượt hữu ích")
    reply_name: str = Field("", description="Tên admin trả lời")
    reply_content: str = Field("", description="Nội dung trả lời")
    images: List[str] = Field(default_factory=list, description="URL ảnh")
    is_active: bool = Field(True, description="Kích hoạt")


class ProductReviewCreate(ProductReviewBase):
    created_at: Optional[datetime] = None
    is_imported: bool = False


class ProductReviewUpdate(BaseModel):
    user_name: Optional[str] = None
    star: Optional[int] = None
    title: Optional[str] = None
    content: Optional[str] = None
    group: Optional[int] = None
    product_id: Optional[int] = None
    useful: Optional[int] = None
    reply_name: Optional[str] = None
    reply_content: Optional[str] = None
    reply_at: Optional[datetime] = None
    images: Optional[List[str]] = None
    is_active: Optional[bool] = None


class ProductReviewResponse(ProductReviewBase):
    id: int
    reply_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_imported: bool = False
    display_created_at: Optional[datetime] = None
    user_has_voted: Optional[bool] = None
    product_slug: Optional[str] = None  # Slug sản phẩm (khách đánh giá) để link Xem sản phẩm
    is_current_user: Optional[bool] = None  # True nếu là đánh giá của user đang đăng nhập (để hiển thị lên đầu)

    class Config:
        from_attributes = True


class ProductReviewListResponse(BaseModel):
    items: List[ProductReviewResponse] = []
    total: int = 0
    skip: int = 0
    limit: int = 10


class UsefulToggleResponse(BaseModel):
    useful: int = Field(..., description="Số lượt hữu ích sau khi toggle")
    user_has_voted: bool = Field(..., description="User đang vote")


class ProductReviewSubmit(BaseModel):
    """Khách hàng gửi đánh giá (cần đăng nhập)"""
    product_id: int = Field(..., description="ID sản phẩm")
    star: int = Field(5, ge=1, le=5, description="Số sao 1-5")
    title: str = Field("", description="Tiêu đề (vd: Cực hài lòng)")
    content: str = Field(..., min_length=1, description="Nội dung đánh giá")
    images: List[str] = Field(default_factory=list, description="URL ảnh (tùy chọn)")
