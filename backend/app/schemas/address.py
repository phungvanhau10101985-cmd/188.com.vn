# backend/app/schemas/address.py - Sổ địa chỉ
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AddressCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=10, max_length=20)
    province: Optional[str] = Field(None, max_length=255)
    district: Optional[str] = Field(None, max_length=255)
    ward: Optional[str] = Field(None, max_length=255)
    street_address: str = Field(..., min_length=5)
    is_default: bool = False


class AddressUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    province: Optional[str] = Field(None, max_length=255)
    district: Optional[str] = Field(None, max_length=255)
    ward: Optional[str] = Field(None, max_length=255)
    street_address: Optional[str] = Field(None, min_length=5)
    is_default: Optional[bool] = None


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
