# backend/app/schemas/user.py - COMPLETE VERSION (PYDANTIC V2)
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class InteractionType(str, Enum):
    VIEW = "view"
    SEARCH = "search"
    CLICK = "click"
    FAVORITE = "favorite"

# ==============================================
# SIMPLIFIED USER SCHEMAS - NO PASSWORD
# ==============================================

class SendRegisterOtpRequest(BaseModel):
    """Gửi OTP đăng ký - chỉ cần phone"""
    phone: str = Field(..., min_length=10, max_length=11, description="Số điện thoại")


class UserCreate(BaseModel):
    """Schema tạo user (ưu tiên email/Gmail)"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=11, description="Số điện thoại 10-11 số, bắt đầu bằng 0")
    date_of_birth: Optional[date] = Field(None, description="Ngày tháng năm sinh (YYYY-MM-DD)")
    full_name: Optional[str] = None
    gender: Optional[Gender] = None
    address: Optional[str] = None
    otp_code: Optional[str] = Field(None, min_length=4, max_length=8, description="Mã OTP đã gửi qua Zalo/Firebase")

    @field_validator('phone', mode='before')
    @classmethod
    def validate_phone(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        if not v.startswith('0'):
            raise ValueError('Số điện thoại phải bắt đầu bằng 0')
        if not v[1:].isdigit():
            raise ValueError('Số điện thoại chỉ được chứa số')
        if len(v) < 10 or len(v) > 11:
            raise ValueError('Số điện thoại phải có 10-11 số')
        return v

    @field_validator('date_of_birth', mode='before')
    @classmethod
    def validate_date_of_birth(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            try:
                v = datetime.strptime(v, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('Ngày sinh phải có định dạng YYYY-MM-DD')
        today = date.today()
        if v > today:
            raise ValueError('Ngày sinh không thể ở tương lai')
        return v

class UserLogin(BaseModel):
    """Legacy login schema (không dùng trong Gmail-only)."""
    phone: Optional[str] = None
    password: Optional[str] = None
    date_of_birth: Optional[str] = None

class UserResponse(BaseModel):
    """Response schema - đầy đủ thông tin"""
    id: int
    phone: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    address: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: Optional[datetime] = None  # DB có thể trả None (server_default)
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    # True khi có admin_users.linked_user_id trùng users.id — vào admin qua menu Cá nhân
    has_linked_admin: bool = False
    # Chi tiết liên kết (admin panel / auth/me khi có quyền)
    linked_admin_role: Optional[str] = None
    linked_admin_username: Optional[str] = None
    linked_admin_modules: Optional[List[str]] = None

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    """Cập nhật thông tin (sau khi đăng ký); ngày sinh / giới tính phục vụ gợi ý & ưu đãi sinh nhật."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = Field(None, description="Ngày sinh (YYYY-MM-DD)")
    gender: Optional[Gender] = None
    address: Optional[str] = None
    avatar: Optional[str] = None

    @field_validator('date_of_birth', mode='before')
    @classmethod
    def validate_dob_update(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            try:
                v = datetime.strptime(v, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('Ngày sinh phải có định dạng YYYY-MM-DD')
        today = date.today()
        if v > today:
            raise ValueError('Ngày sinh không thể ở tương lai')
        return v


class UserAdminUpdate(BaseModel):
    """Admin: cập nhật thành viên (is_active, thông tin cơ bản)"""
    is_active: Optional[bool] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None


class GoogleLoginRequest(BaseModel):
    """Google OAuth login request"""
    id_token: str = Field(..., description="Google ID token")
    # Cùng mã thiết bị với luồng email OTP: sau khi đăng nhập Google, lần sau có thể dùng try-trusted-device bằng email (cùng trình duyệt)
    device_id: Optional[str] = Field(None, min_length=8, max_length=128, description="Device id (trình duyệt)")

    @field_validator("device_id", mode="before")
    @classmethod
    def strip_g_device(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class SendEmailOtpRequest(BaseModel):
    """Gửi mã OTP đăng nhập tới email"""
    email: EmailStr


class VerifyEmailOtpRequest(BaseModel):
    """Xác nhận mã OTP đã nhận qua email"""
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=8, description="Mã OTP")
    # Mã thiết bị (localStorage) — sau lần xác thực thành công, thiết bị được lưu để lần sau đăng nhập không cần OTP (cùng trình duyệt)
    device_id: Optional[str] = Field(None, min_length=8, max_length=128, description="Device id (trình duyệt)")

    @field_validator("device_id", mode="before")
    @classmethod
    def strip_device(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class TryTrustedDeviceRequest(BaseModel):
    """Thử đăng nhập chỉ bằng email nếu thiết bị đã từng xác thực OTP (cùng trình duyệt)"""
    email: EmailStr
    device_id: str = Field(..., min_length=8, max_length=128, description="Cùng mã thiết bị lưu trong trình duyệt")


class TryTrustedDeviceResponse(BaseModel):
    ok: bool
    require_otp: bool = True
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class AdminUsersListResponse(BaseModel):
    """Admin: danh sách thành viên (items + total)"""
    items: List[UserResponse]
    total: int

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class ForgotDateOfBirthRequest(BaseModel):
    """Quên ngày sinh - cần phone và otp_code (sau khi gửi OTP)."""
    phone: str = Field(..., min_length=10, max_length=11)
    otp_code: str = Field(..., min_length=4, max_length=8)


class DateOfBirthResponse(BaseModel):
    phone: str
    date_of_birth: date
    full_name: str

# ==============================================
# USER BEHAVIOR SCHEMAS
# ==============================================

class ProductViewCreate(BaseModel):
    """Schema để tạo/xem sản phẩm"""
    product_id: int = Field(..., description="ID sản phẩm")
    product_data: Optional[Dict[str, Any]] = Field(None, description="Dữ liệu sản phẩm đầy đủ")
    time_spent_seconds: Optional[int] = Field(0, description="Thời gian xem (giây)")
    
    class Config:
        from_attributes = True

class FavoriteCreate(BaseModel):
    """Schema để thêm sản phẩm yêu thích"""
    product_id: int = Field(..., description="ID sản phẩm")
    product_data: Optional[Dict[str, Any]] = Field(None, description="Dữ liệu sản phẩm đầy đủ")
    
    class Config:
        from_attributes = True

class CategoryViewCreate(BaseModel):
    """Schema để xem danh mục"""
    category_id: int = Field(..., description="ID danh mục")
    category_name: Optional[str] = Field(None, description="Tên danh mục")
    
    class Config:
        from_attributes = True

class BrandViewCreate(BaseModel):
    """Schema để xem thương hiệu"""
    brand_name: str = Field(..., description="Tên thương hiệu")
    
    class Config:
        from_attributes = True

class SearchHistoryCreate(BaseModel):
    """Schema để lưu lịch sử tìm kiếm"""
    search_query: str = Field(..., description="Từ khóa tìm kiếm")
    search_filters: Optional[Dict[str, Any]] = Field(None, description="Bộ lọc tìm kiếm")
    search_results_count: Optional[int] = Field(0, description="Số kết quả tìm thấy")
    
    class Config:
        from_attributes = True

class ShopInteractionCreate(BaseModel):
    """Schema để tương tác với shop"""
    shop_name: str = Field(..., description="Tên shop")
    shop_id: Optional[str] = Field(None, description="ID shop")
    shop_search_url: Optional[str] = Field(None, description="URL tìm kiếm shop")
    shop_id_search_url: Optional[str] = Field(None, description="URL tìm kiếm bằng ID shop")
    related_cheaper_search_url: Optional[str] = Field(None, description="URL tìm sản phẩm rẻ hơn")
    related_expensive_search_url: Optional[str] = Field(None, description="URL tìm sản phẩm đắt hơn")
    interaction_type: InteractionType = Field(..., description="Loại tương tác")
    
    class Config:
        from_attributes = True

class ProductViewResponse(ProductViewCreate):
    id: int
    user_id: Optional[int] = None  # None khi dữ liệu từ phiên khách
    viewed_at: Optional[datetime] = None  # DB có thể trả None
    
    class Config:
        from_attributes = True

class FavoriteResponse(FavoriteCreate):
    id: int
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None  # DB có thể trả None → fix Pydantic datetime_type
    
    class Config:
        from_attributes = True

class CategoryViewResponse(CategoryViewCreate):
    id: int
    user_id: int
    viewed_at: Optional[datetime] = None
    view_count: int = 1
    
    class Config:
        from_attributes = True

class BrandViewResponse(BrandViewCreate):
    id: int
    user_id: int
    viewed_at: Optional[datetime] = None
    view_count: int = 1
    
    class Config:
        from_attributes = True

class SearchHistoryResponse(SearchHistoryCreate):
    id: int
    user_id: Optional[int] = None
    searched_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ShopInteractionResponse(ShopInteractionCreate):
    id: int
    user_id: int
    interacted_at: Optional[datetime] = None
    interaction_count: int = 1
    
    class Config:
        from_attributes = True

class UserBehaviorStats(BaseModel):
    """Schema cho thống kê hành vi người dùng đầy đủ"""
    total_products_viewed: int
    total_favorites: int
    total_categories_viewed: int
    total_brands_viewed: int
    total_searches: int
    total_shop_interactions: int
    recently_viewed_products: List[ProductViewResponse]
    favorite_products: List[FavoriteResponse]
    recently_viewed_categories: List[CategoryViewResponse]
    recently_viewed_brands: List[BrandViewResponse]
    recent_searches: List[SearchHistoryResponse]
    recent_shop_interactions: List[ShopInteractionResponse]
    
    class Config:
        from_attributes = True
