from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.core.security import get_current_user
from app.models.user import User
from app.models.push_subscription import UserPushSubscription
from app.schemas.push import PushSubscribeIn, PushUnsubscribeIn, VapidPublicOut, OkOut
from app.services import push_service

router = APIRouter()


@router.get("/vapid-public-key", response_model=VapidPublicOut)
def get_vapid_public():
    k = (settings.VAPID_PUBLIC_KEY or "").strip()
    if not k or not (settings.VAPID_PRIVATE_KEY or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình Web Push (VAPID).",
        )
    return {"public_key": k}


@router.post("/subscribe", response_model=OkOut)
def subscribe_push(
    body: PushSubscribeIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not push_service.is_push_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình VAPID.",
        )
    ua = body.user_agent or (request.headers.get("user-agent", "") or "")[:500]
    row = (
        db.query(UserPushSubscription)
        .filter(UserPushSubscription.endpoint == body.endpoint)
        .first()
    )
    if row:
        row.user_id = current_user.id
        row.p256dh = body.keys.p256dh
        row.auth = body.keys.auth
        row.user_agent = ua
    else:
        row = UserPushSubscription(
            user_id=current_user.id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            user_agent=ua,
        )
        db.add(row)
    db.commit()
    return OkOut(ok=True, message="Đã bật thông báo trên thiết bị này.")


@router.post("/unsubscribe", response_model=OkOut)
def unsubscribe_push(
    body: PushUnsubscribeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = (
        db.query(UserPushSubscription)
        .filter(
            UserPushSubscription.user_id == current_user.id,
            UserPushSubscription.endpoint == body.endpoint,
        )
        .delete()
    )
    db.commit()
    return OkOut(ok=True, message="Đã tắt" if n else "Không tìm thấy")
