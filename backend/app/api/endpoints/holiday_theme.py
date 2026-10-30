"""Chủ đề ngày lễ storefront — public, cache ngắn."""
from fastapi import APIRouter, HTTPException, Query

from app.crud import holiday_theme as holiday_theme_crud
from app.db.session import SessionLocal
from app.schemas.holiday_theme import HolidayPreviewCheckOut, HolidayThemePublicOut
from app.services.holiday_preview_grant import parse_holiday_preview_token
from app.utils.ttl_cache import cache as ttl_cache

router = APIRouter()

_PUBLIC_TTL = 20.0


def _fetch_public() -> HolidayThemePublicOut:
    db = SessionLocal()
    try:
        return holiday_theme_crud.public_theme_out(db=db)
    finally:
        db.close()


@router.get("/preview", response_model=HolidayPreviewCheckOut)
def check_holiday_preview(token: str = Query(..., min_length=8, max_length=120)):
    """Xác nhận mã xem trước do admin vừa cấp. Không có mã hợp lệ thì cửa hàng giữ giao diện thường."""
    parsed = parse_holiday_preview_token(token)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Bản xem trước không còn hiệu lực")
    code, expires_at = parsed
    return HolidayPreviewCheckOut(code=code, expires_at=expires_at)


@router.get("/public", response_model=HolidayThemePublicOut)
def get_public_holiday_theme():
    """Chủ đề đang bật. null = giao diện thường. Cache 20 giây."""
    return ttl_cache.get_or_fetch(
        holiday_theme_crud.HOLIDAY_THEME_PUBLIC_CACHE_KEY,
        _PUBLIC_TTL,
        _fetch_public,
    )
