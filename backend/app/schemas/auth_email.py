# Schemas cho luồng POST /auth/email/request, verify-otp
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import UserResponse


class EmailAuthRequestBody(BaseModel):
    email: EmailStr
    next: Optional[str] = Field(None, max_length=512, description="Đường dẫn tương đối sau đăng nhập, ví dụ /account")
    remember_device: bool = False
    browser_id: Optional[str] = Field(None, min_length=8, max_length=256)

    @field_validator("browser_id", mode="before")
    @classmethod
    def strip_browser(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None


class EmailAuthVerifyOtpBody(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=8)
    remember_device: bool = False
    browser_id: Optional[str] = Field(None, min_length=8, max_length=256)
    next: Optional[str] = Field(None, max_length=512)

    @field_validator("browser_id", mode="before")
    @classmethod
    def strip_browser(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    @field_validator("otp", mode="before")
    @classmethod
    def strip_otp(cls, v):
        return str(v).strip() if v is not None else ""


class EmailAuthRequestResponse(BaseModel):
    auto_signed_in: bool
    next: str = "/"
    message: Optional[str] = None
    user: Optional[UserResponse] = None
    # Thêm cho SPA: api-client dùng Bearer; cookie httpOnly vẫn được set song song
    access_token: Optional[str] = None
    token_type: str = "bearer"


class EmailAuthVerifyResponse(BaseModel):
    auto_signed_in: bool = True
    next: str = "/"
    user: Optional[UserResponse] = None
    access_token: Optional[str] = None
    token_type: str = "bearer"
