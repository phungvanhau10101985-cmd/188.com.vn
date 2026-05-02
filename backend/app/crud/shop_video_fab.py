from sqlalchemy.orm import Session

from app.models.shop_video_fab_setting import ShopVideoFabSetting
from app.schemas.shop_video_fab import ShopVideoFabAdminUpdate, ShopVideoFabPublicOut
from app.utils.ttl_cache import cache as ttl_cache

SHOP_VIDEO_FAB_PUBLIC_CACHE_KEY = "shop_video_fab_v1:public"

_SINGLETON_ID = 1

_DEFAULT = dict(
    right_mobile_px=16,
    bottom_mobile_px_no_nav=16,
    bottom_mobile_px_with_nav=144,
    right_desktop_px=32,
    bottom_desktop_px=40,
)


def invalidate_public_cache() -> None:
    ttl_cache.invalidate(SHOP_VIDEO_FAB_PUBLIC_CACHE_KEY)


def row_to_public_out(row: ShopVideoFabSetting) -> ShopVideoFabPublicOut:
    return ShopVideoFabPublicOut(
        right_mobile_px=row.right_mobile_px,
        bottom_mobile_px_no_nav=row.bottom_mobile_px_no_nav,
        bottom_mobile_px_with_nav=row.bottom_mobile_px_with_nav,
        right_desktop_px=row.right_desktop_px,
        bottom_desktop_px=row.bottom_desktop_px,
    )


def get_or_create_singleton(db: Session) -> ShopVideoFabSetting:
    row = db.query(ShopVideoFabSetting).filter(ShopVideoFabSetting.id == _SINGLETON_ID).first()
    if row:
        return row
    row = ShopVideoFabSetting(id=_SINGLETON_ID, **_DEFAULT)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_singleton(db: Session, data: ShopVideoFabAdminUpdate) -> ShopVideoFabPublicOut:
    row = get_or_create_singleton(db)
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_public_cache()
    return row_to_public_out(row)
