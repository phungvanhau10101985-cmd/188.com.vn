# Mã nhúng công khai (GA, Pixel…) + Meta Conversion API (máy chủ)
import logging
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import site_embed_code as embed_crud
from app.db.session import get_db
from app.schemas.site_embed_code import FacebookCapiEventIn, PublicSiteEmbedsResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/public", response_model=PublicSiteEmbedsResponse)
def get_public_site_embeds(db: Session = Depends(get_db)):
    """Trả các đoạn mã nhúng đang bật, gom theo vị trí (head / body_open / body_close)."""
    head, body_open, body_close = embed_crud.collect_public_snippets(db)
    return PublicSiteEmbedsResponse(head=head, body_open=body_open, body_close=body_close)


def _verify_facebook_capi_ingest(authorization: Optional[str] = Header(None)) -> None:
    secret = getattr(settings, "FACEBOOK_CAPI_INGEST_SECRET", "") or ""
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Chưa bật: đặt biến môi trường FACEBOOK_CAPI_INGEST_SECRET trên backend.",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Thiếu Authorization: Bearer <cùng giá trị FACEBOOK_CAPI_INGEST_SECRET>",
        )
    token = authorization[7:].strip()
    if token != secret:
        raise HTTPException(status_code=403, detail="Unauthorized")


@router.post("/facebook/capi/send-event")
def facebook_capi_send_event(
    payload: FacebookCapiEventIn,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_facebook_capi_ingest),
):
    """
    Gửi một sự kiện sang Meta Graph (Conversions API). Đích: pixel_id + access_token trong admin.

    Frontend / app khác gọi (server-to-server):
    Authorization: Bearer <FACEBOOK_CAPI_INGEST_SECRET>
    """
    pix, access_token = embed_crud.get_facebook_pixel_id_and_capi_access_token(db)
    if not pix or not access_token:
        raise HTTPException(
            status_code=400,
            detail="Chưa cấu hình trong admin: Facebook Pixel ID + Conversion API Access Token (đang bật).",
        )

    event_time = int(payload.event_time) if payload.event_time else int(time.time())
    evt: dict = {
        "event_name": payload.event_name,
        "event_time": event_time,
        "action_source": payload.action_source or "website",
    }
    if payload.event_id:
        evt["event_id"] = payload.event_id.strip()[:128]
    if payload.custom_data:
        evt["custom_data"] = payload.custom_data
    if payload.user_data:
        evt["user_data"] = payload.user_data

    ver = getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "v21.0")
    url = f"https://graph.facebook.com/{ver}/{pix}/events"
    try:
        r = requests.post(
            url,
            params={"access_token": access_token},
            json={"data": [evt]},
            timeout=30,
        )
    except requests.RequestException as e:
        logger.exception("Facebook CAPI request failed")
        raise HTTPException(status_code=502, detail=f"Lỗi kết nối Meta: {e!s}") from e

    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:2000]}

    if not r.ok:
        logger.warning("Facebook CAPI HTTP %s: %s", r.status_code, body)
        raise HTTPException(status_code=r.status_code if r.status_code < 500 else 502, detail=body)

    return {"ok": True, "meta": body}
