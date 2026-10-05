from pydantic import BaseModel, Field


class DepositPercentOut(BaseModel):
    """Mức cọc một phần (1–99) và sàn tiền cọc. Cọc 100% là lựa chọn riêng."""

    partial_percent: int = Field(..., ge=1, le=99)
    min_amount: int = Field(..., ge=100_000, le=50_000_000)


class DepositPercentUpdate(BaseModel):
    partial_percent: int = Field(..., ge=1, le=99)
    min_amount: int = Field(..., ge=100_000, le=50_000_000)
