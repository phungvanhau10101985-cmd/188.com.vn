from typing import Optional

from pydantic import BaseModel, Field


class DepositPercentOut(BaseModel):
    """Hai mức cọc theo mốc giá trị hàng. Cọc 100% là lựa chọn riêng."""

    partial_percent: int = Field(..., ge=1, le=99)
    min_amount: int = Field(..., ge=100_000, le=50_000_000)
    high_order_amount: int = Field(..., ge=100_000, le=500_000_000)
    high_order_percent: int = Field(..., ge=1, le=99)


class DepositPercentUpdate(BaseModel):
    partial_percent: int = Field(..., ge=1, le=99)
    min_amount: int = Field(..., ge=100_000, le=50_000_000)
    # Thiếu field thì giữ số đang lưu — form cũ chỉ gửi % và sàn tiền vẫn lưu được.
    high_order_amount: Optional[int] = Field(None, ge=100_000, le=500_000_000)
    high_order_percent: Optional[int] = Field(None, ge=1, le=99)
