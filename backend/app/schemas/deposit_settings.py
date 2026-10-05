from pydantic import BaseModel, Field


class DepositPercentOut(BaseModel):
    """Mức cọc một phần đang áp dụng (1–99). Cọc 100% là lựa chọn riêng."""

    partial_percent: int = Field(..., ge=1, le=99)


class DepositPercentUpdate(BaseModel):
    partial_percent: int = Field(..., ge=1, le=99)
