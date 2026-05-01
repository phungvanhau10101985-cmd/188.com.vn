from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime

class CartItemBase(BaseModel):
    product_id: int = Field(..., description="ID sản phẩm")
    quantity: int = Field(1, ge=1, le=100, description="Số lượng")
    selected_size: Optional[str] = Field(None, description="Size được chọn")
    selected_color: Optional[str] = Field(None, description="Mã màu")
    selected_color_name: Optional[str] = Field(None, description="Tên màu")

class CartItemCreate(CartItemBase):
    product_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Snapshot từ client (main_image theo biến thể, slug, …)",
    )
    line_image_url: Optional[str] = Field(
        None,
        max_length=2000,
        description="URL ảnh đúng biến thể — ưu tiên khi lưu giỏ",
    )


class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, le=100, description="Số lượng mới")
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    selected_color_name: Optional[str] = None

class CartItemResponse(CartItemBase):
    selected_color_name: Optional[str] = None
    id: int
    cart_id: Optional[int] = None  # Có thể là None hoặc user_id
    user_id: int
    product_code: Optional[str] = None
    product_name: str
    product_price: float
    product_image: Optional[str] = None
    product_data: Optional[Dict[str, Any]] = None
    requires_deposit: bool = False
    created_at: Optional[datetime] = None  # SQLite/server_default có thể trả None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class CartResponse(BaseModel):
    id: Optional[int] = None  # Cart có thể chưa được tạo (hoặc dùng user_id)
    user_id: int
    total_items: int = 0
    total_price: float = 0.0
    items_count: int = 0
    requires_deposit: bool = False
    items: List[CartItemResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Loyalty fields
    loyalty_discount_percent: float = 0.0
    loyalty_discount_amount: float = 0.0
    final_price: float = 0.0
    loyalty_tier_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class GuestCartItem(BaseModel):
    product_id: int
    quantity: int
    selected_size: Optional[str] = None
    selected_color: Optional[str] = None
    selected_color_name: Optional[str] = None
    product_data: Dict[str, Any]
    unit_price: float
    added_at: str

class GuestCartMigration(BaseModel):
    guest_items: List[GuestCartItem] = Field(..., description="Cart items từ localStorage")

class CartMergeResponse(BaseModel):
    message: str
    migrated_items: int
    total_items: int
    cart: CartResponse

# For bulk operations
class BulkCartUpdate(BaseModel):
    items: List[CartItemCreate]
    
    @validator('items')
    def validate_items_limit(cls, v):
        if len(v) > 50:
            raise ValueError('Không thể thêm quá 50 sản phẩm cùng lúc')
        return v

# ========== BACKWARD COMPATIBILITY ==========
# Alias để duy trì tương thích với code cũ
CartItem = CartItemBase
