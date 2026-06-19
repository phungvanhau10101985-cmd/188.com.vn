"""Google Merchant Center — API hỗ trợ chiết khấu tự động."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.google_automated_discount import (
    GoogleAutomatedDiscountError,
    automated_discount_enabled,
    verify_google_automated_discount_token,
)

router = APIRouter()


class AutomatedDiscountVerifyRequest(BaseModel):
    token: str = Field(..., min_length=10, description="JWT pv2 từ URL quảng cáo Mua sắm")
    offer_id: Optional[str] = Field(None, description="product_id trong feed (trường id GMC)")


class AutomatedDiscountVerifyResponse(BaseModel):
    valid: bool = True
    price: float
    prior_price: Optional[float] = None
    currency: str
    offer_id: str
    merchant_id: str
    expires_at: int


@router.post(
    "/automated-discount/verify",
    response_model=AutomatedDiscountVerifyResponse,
    summary="Xác thực JWT pv2 — chiết khấu tự động Google Shopping",
)
def verify_automated_discount_token(body: AutomatedDiscountVerifyRequest):
    if not automated_discount_enabled():
        raise HTTPException(status_code=503, detail="Chiết khấu tự động Google chưa được bật trên hệ thống.")
    try:
        payload = verify_google_automated_discount_token(
            body.token,
            expected_offer_id=body.offer_id,
        )
    except GoogleAutomatedDiscountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AutomatedDiscountVerifyResponse(
        price=payload.price,
        prior_price=payload.prior_price,
        currency=payload.currency,
        offer_id=payload.offer_id,
        merchant_id=payload.merchant_id,
        expires_at=payload.expires_at,
    )
