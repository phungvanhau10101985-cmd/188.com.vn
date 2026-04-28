# backend/app/schemas/bank_account.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BankAccountCreate(BaseModel):
    bank_name: str = Field(..., min_length=1, max_length=255)
    account_number: str = Field(..., min_length=1, max_length=50)
    account_holder: str = Field(..., min_length=1, max_length=255)
    bank_code: Optional[str] = Field(None, max_length=32)
    qr_template_url: Optional[str] = None
    branch: Optional[str] = Field(None, max_length=255)
    note: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class BankAccountUpdate(BaseModel):
    bank_name: Optional[str] = Field(None, max_length=255)
    account_number: Optional[str] = Field(None, max_length=50)
    account_holder: Optional[str] = Field(None, max_length=255)
    bank_code: Optional[str] = Field(None, max_length=32)
    qr_template_url: Optional[str] = None
    branch: Optional[str] = Field(None, max_length=255)
    note: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class BankAccountResponse(BaseModel):
    id: int
    bank_name: str
    account_number: str
    account_holder: str
    bank_code: Optional[str] = None
    qr_template_url: Optional[str] = None
    branch: Optional[str] = None
    note: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
