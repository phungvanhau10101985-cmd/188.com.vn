import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.marketing_email import (
    MarketingUnsubscribeRequest,
    MarketingUnsubscribeResponse,
)
from app.services.marketing_email_unsubscribe import (
    parse_unsubscribe_token,
    unsubscribe_marketing_email,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _unsubscribe_with_token(db: Session, token: str) -> MarketingUnsubscribeResponse:
    email = parse_unsubscribe_token(token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Liên kết ngừng nhận tin không hợp lệ hoặc đã hết hạn.",
        )
    try:
        created, masked = unsubscribe_marketing_email(db, email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if created:
        message = (
            "Bạn đã ngừng nhận tin khuyến mãi từ 188.com.vn. "
            "Email về đơn hàng, giao hàng và xác minh tài khoản vẫn được gửi bình thường."
        )
    else:
        message = (
            "Email này đã được ghi nhận ngừng nhận tin khuyến mãi trước đó. "
            "Email đơn hàng vẫn được gửi bình thường."
        )
    logger.info("marketing_unsubscribe email=%s created=%s", masked, created)
    return MarketingUnsubscribeResponse(
        ok=True,
        message=message,
        email_masked=masked,
        already_unsubscribed=not created,
    )


@router.get("/unsubscribe", response_model=MarketingUnsubscribeResponse)
def unsubscribe_marketing_get(
    token: str = Query(..., min_length=8, max_length=512),
    db: Session = Depends(get_db),
):
    """Ngừng nhận tin khuyến mãi — gọi từ trang /email/ngung-nhan-tin."""
    return _unsubscribe_with_token(db, token)


@router.post("/unsubscribe", response_model=MarketingUnsubscribeResponse)
def unsubscribe_marketing_post(
    body: MarketingUnsubscribeRequest,
    db: Session = Depends(get_db),
):
    """Ngừng nhận tin khuyến mãi — POST (tuỳ chọn)."""
    return _unsubscribe_with_token(db, body.token)
