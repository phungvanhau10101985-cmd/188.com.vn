"""FAB lướt video shop — cấu hình vị trí (public + cache TTL)."""
from fastapi import APIRouter

from app.crud import shop_video_fab as shop_video_fab_crud
from app.db.session import SessionLocal
from app.schemas.shop_video_fab import ShopVideoFabPublicOut
from app.utils.ttl_cache import cache as ttl_cache

router = APIRouter()

_SHOP_VIDEO_FAB_PUBLIC_TTL = 60.0


def _fetch_public_fab() -> ShopVideoFabPublicOut:
    db = SessionLocal()
    try:
        row = shop_video_fab_crud.get_or_create_singleton(db)
        return shop_video_fab_crud.row_to_public_out(row)
    finally:
        db.close()


@router.get("/public", response_model=ShopVideoFabPublicOut)
def get_public_shop_video_fab():
    """Vị trí nút video (pixel). Cache 60s giống embed-codes public."""
    return ttl_cache.get_or_fetch(
        shop_video_fab_crud.SHOP_VIDEO_FAB_PUBLIC_CACHE_KEY,
        _SHOP_VIDEO_FAB_PUBLIC_TTL,
        _fetch_public_fab,
    )
