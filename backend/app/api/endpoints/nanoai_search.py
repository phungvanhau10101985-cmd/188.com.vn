# NanoAI — proxy tìm sản phẩm theo ảnh / chữ (Bearer chỉ env server).
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services import nanoai_partner_search as nanoai
from app.services.nanoai_catalog_enrich import enrich_nanoai_response_body

logger = logging.getLogger(__name__)

router = APIRouter()


class TextSearchBody(BaseModel):
    q: str = Field(..., min_length=2)
    limit: int = Field(50, ge=1, le=100)


class NanoAiCustomerTokenResponse(BaseModel):
    token: Optional[str] = None
    expires_at: Optional[int] = None


def _trim_optional_text(value: object, max_len: int) -> Optional[str]:
    text = str(value or "").strip()
    return text[:max_len] if text else None


def _build_partner_customer_token(user: User) -> NanoAiCustomerTokenResponse:
    email = str(user.email or "").strip().lower()
    if not email:
        return NanoAiCustomerTokenResponse(token=None, expires_at=None)

    embed_key = settings.NANOAI_EMBED_KEY
    if not embed_key:
        raise HTTPException(
            status_code=503,
            detail="NanoAI auto-login chưa cấu hình NANOAI_EMBED_KEY trên server.",
        )

    exp = int(time.time()) + 300
    sig = hmac.new(embed_key.encode("utf-8"), f"{email}|{exp}".encode("utf-8"), hashlib.sha256).hexdigest()
    payload: dict[str, object] = {"email": email, "exp": exp, "sig": sig}

    name = _trim_optional_text(user.full_name, 180)
    phone = _trim_optional_text(user.phone, 40)
    if name:
        payload["name"] = name
    if phone:
        payload["phone"] = phone

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return NanoAiCustomerTokenResponse(token=token, expires_at=exp)


def _empty_search_response(error: str | None = None) -> dict:
    return {"ok": error is None, "products": [], "error": error}


def _not_configured():
    raise HTTPException(
        status_code=503,
        detail="Tìm theo ảnh NanoAI chưa cấu hình (NANOAI_PARTNER_ID / NANOAI_BEARER_TOKEN).",
    )


@router.post("/image-search")
async def image_search(
    file: UploadFile = File(...),
    limit: int = Form(24),
    db: Session = Depends(get_db),
):
    if not nanoai.is_configured():
        _not_configured()
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit phải từ 1 đến 100")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Thiếu file ảnh")
    if len(raw) > nanoai.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Ảnh vượt quá ~5 MB")
    status, body = nanoai.post_image_search(
        raw,
        file.filename or "image.jpg",
        file.content_type,
        limit,
    )
    if status == 200:
        try:
            return enrich_nanoai_response_body(db, body)
        except Exception:
            logger.exception("NanoAI image-search enrichment failed")
            db.rollback()
            if isinstance(body, dict):
                return body
            return _empty_search_response("Không xử lý được kết quả NanoAI.")
    logger.warning("NanoAI image-search returned status %s: %s", status, body)
    return _empty_search_response(nanoai.extract_nanoai_error(body))


@router.get("/customer-token", response_model=NanoAiCustomerTokenResponse)
def customer_token(current_user: User = Depends(get_current_user)):
    """Ký token ngắn hạn để widget NanoAI nhận diện khách đã đăng nhập shop."""
    return _build_partner_customer_token(current_user)


@router.post("/text-search")
async def text_search(body: TextSearchBody, db: Session = Depends(get_db)):
    if not nanoai.is_configured():
        return _empty_search_response("Tìm theo chữ NanoAI chưa cấu hình.")
    try:
        status, resp = nanoai.post_text_search(body.q.strip(), body.limit)
    except Exception:
        logger.exception("NanoAI text-search proxy failed")
        return _empty_search_response("NanoAI tạm thời không phản hồi.")
    if status == 200:
        try:
            return enrich_nanoai_response_body(db, resp)
        except Exception:
            logger.exception("NanoAI text-search enrichment failed")
            db.rollback()
            return resp if isinstance(resp, dict) else _empty_search_response(None)
    logger.warning("NanoAI text-search returned status %s: %s", status, resp)
    if isinstance(resp, dict):
        return _empty_search_response(str(resp.get("error") or resp.get("detail") or "NanoAI tạm thời không phản hồi."))
    return _empty_search_response(str(resp)[:300] if resp else "NanoAI tạm thời không phản hồi.")
