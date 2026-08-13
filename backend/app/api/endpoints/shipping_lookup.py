"""Cổng API tra cứu vận chuyển — partner / chatbot / hệ thống ngoài."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.shipping_lookup import ShippingLookupRequest, ShippingLookupResponse
from app.services import shipping_lookup as lookup_svc

router = APIRouter()


def _require_key(request: Request) -> None:
    lookup_svc.verify_shipping_lookup_auth(request)


@router.get(
    "/lookup",
    response_model=ShippingLookupResponse,
    summary="Tra cứu vận chuyển (GET)",
)
def shipping_lookup_get(
    q: Optional[str] = Query(default=None, max_length=80, description="Mã đơn DH…, SĐT, hoặc mã EMS"),
    order_code: Optional[str] = Query(default=None, max_length=50),
    phone: Optional[str] = Query(default=None, max_length=20),
    ems_code: Optional[str] = Query(default=None, max_length=50),
    db: Session = Depends(get_db),
    _: None = Depends(_require_key),
):
    return lookup_svc.lookup_shipping(
        db,
        q=q,
        order_code=order_code,
        phone=phone,
        ems_code=ems_code,
    )


@router.post(
    "/lookup",
    response_model=ShippingLookupResponse,
    summary="Tra cứu vận chuyển (POST)",
)
def shipping_lookup_post(
    body: ShippingLookupRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_key),
):
    return lookup_svc.lookup_shipping(
        db,
        q=body.q,
        order_code=body.order_code,
        phone=body.phone,
        ems_code=body.ems_code,
    )
