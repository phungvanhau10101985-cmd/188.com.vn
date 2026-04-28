# NanoAI — proxy tìm sản phẩm theo ảnh / chữ (Bearer chỉ env server).
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import nanoai_partner_search as nanoai
from app.services.nanoai_catalog_enrich import enrich_nanoai_response_body

logger = logging.getLogger(__name__)

router = APIRouter()


class TextSearchBody(BaseModel):
    q: str = Field(..., min_length=2)
    limit: int = Field(50, ge=1, le=100)


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
        return enrich_nanoai_response_body(db, body)
    if isinstance(body, dict):
        return JSONResponse(content=body, status_code=status)
    return JSONResponse(content={"detail": str(body)}, status_code=status)


@router.post("/text-search")
async def text_search(body: TextSearchBody, db: Session = Depends(get_db)):
    if not nanoai.is_configured():
        _not_configured()
    status, resp = nanoai.post_text_search(body.q.strip(), body.limit)
    if status == 200:
        return enrich_nanoai_response_body(db, resp)
    if isinstance(resp, dict):
        return JSONResponse(content=resp, status_code=status)
    return JSONResponse(content={"detail": str(resp)}, status_code=status)
