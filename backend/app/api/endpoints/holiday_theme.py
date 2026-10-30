"""Chủ đề ngày lễ storefront — public, cache ngắn."""
from fastapi import APIRouter

from app.crud import holiday_theme as holiday_theme_crud
from app.db.session import SessionLocal
from app.schemas.holiday_theme import HolidayThemePublicOut
from app.utils.ttl_cache import cache as ttl_cache

router = APIRouter()

_PUBLIC_TTL = 20.0


def _fetch_public() -> HolidayThemePublicOut:
    db = SessionLocal()
    try:
        return holiday_theme_crud.public_theme_out(db=db)
    finally:
        db.close()


@router.get("/public", response_model=HolidayThemePublicOut)
def get_public_holiday_theme():
    """Chủ đề đang bật. null = giao diện thường. Cache 20 giây."""
    return ttl_cache.get_or_fetch(
        holiday_theme_crud.HOLIDAY_THEME_PUBLIC_CACHE_KEY,
        _PUBLIC_TTL,
        _fetch_public,
    )
