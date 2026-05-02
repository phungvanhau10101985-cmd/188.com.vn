from pydantic import BaseModel, Field


class ShopVideoFabPublicOut(BaseModel):
    """Vị trí FAB video (pixel) — API public + admin GET."""

    right_mobile_px: int = Field(..., ge=0, le=400)
    bottom_mobile_px_no_nav: int = Field(..., ge=0, le=400)
    bottom_mobile_px_with_nav: int = Field(..., ge=0, le=400)
    right_desktop_px: int = Field(..., ge=0, le=400)
    bottom_desktop_px: int = Field(..., ge=0, le=400)

    class Config:
        from_attributes = True


class ShopVideoFabAdminUpdate(BaseModel):
    right_mobile_px: int | None = Field(None, ge=0, le=400)
    bottom_mobile_px_no_nav: int | None = Field(None, ge=0, le=400)
    bottom_mobile_px_with_nav: int | None = Field(None, ge=0, le=400)
    right_desktop_px: int | None = Field(None, ge=0, le=400)
    bottom_desktop_px: int | None = Field(None, ge=0, le=400)
