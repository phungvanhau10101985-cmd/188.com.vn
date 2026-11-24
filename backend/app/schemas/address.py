# backend/app/schemas/address.py - Sổ địa chỉ
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


def normalize_vn_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    if len(digits) == 9:
        digits = "0" + digits
    if not re.fullmatch(r"0\d{9,10}", digits):
        raise ValueError("Số điện thoại phải có 10 số, bắt đầu bằng 0")
    return digits


class AddressCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., max_length=20)
    province: Optional[str] = Field(None, max_length=255)
    district: Optional[str] = Field(None, max_length=255)
    ward: Optional[str] = Field(None, max_length=255)
    street_address: str = Field(..., max_length=1000)
    is_default: bool = False

    @field_validator("full_name", "province", "district", "ward", mode="before")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def phone_ok(cls, value):
        return normalize_vn_phone(str(value or ""))

    @field_validator("street_address", mode="before")
    @classmethod
    def street_ok(cls, value):
        text = str(value or "").strip()
        if len(text) < 5:
            raise ValueError("Địa chỉ cụ thể cần ít nhất 5 ký tự")
        return text


class AddressUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    province: Optional[str] = Field(None, max_length=255)
    district: Optional[str] = Field(None, max_length=255)
    ward: Optional[str] = Field(None, max_length=255)
    street_address: Optional[str] = Field(None, max_length=1000)
    is_default: Optional[bool] = None

    @field_validator("full_name", "province", "district", "ward", mode="before")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @field_validator("phone", mode="before")
    @classmethod
    def phone_ok(cls, value):
        if value is None:
            return None
        return normalize_vn_phone(str(value))

    @field_validator("street_address", mode="before")
    @classmethod
    def street_ok(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        if len(text) < 5:
            raise ValueError("Địa chỉ cụ thể cần ít nhất 5 ký tự")
        return text


class AddressResponse(BaseModel):
    id: int
    user_id: int
    full_name: str
    phone: str
    province: Optional[str] = None
    district: Optional[str] = None
    ward: Optional[str] = None
    street_address: str
    is_default: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
