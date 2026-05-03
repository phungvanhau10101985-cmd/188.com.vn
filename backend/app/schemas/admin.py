# backend/app/schemas/admin.py
from pydantic import BaseModel, Field
from typing import Optional

class AdminLogin(BaseModel):
    username: str = Field(..., description="Tên đăng nhập")
    password: str = Field(..., description="Mật khẩu")

class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin_id: int
    username: str
    role: str

class AdminCreate(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "admin"
    linked_user_id: Optional[int] = Field(None, description="users.id — đăng nhập khách có thể vào admin qua menu")

class AdminUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
