from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

HolidayThemeId = str


class HolidayThemePublicOut(BaseModel):
    active_theme: Optional[str] = None
    event_year: Optional[int] = None
    event_year_end: Optional[int] = None
    occasion_years: dict[str, int] = Field(default_factory=dict)


class HolidayOccasionOut(BaseModel):
    code: str
    name: str
    calendar: Literal["solar", "lunar"]
    calendar_label: str
    tagline: str
    summary: str
    start_month: int
    start_day: int
    end_month: int
    end_day: int
    lead_days: int
    after_days: int
    sale_percent: float
    enabled: bool
    priority: int
    solar_label: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    showing_today: bool = False


class HolidayThemeAdminOut(BaseModel):
    active_theme: Optional[str] = None
    active_label: Optional[str] = None
    schedule_note: str = ""
    occasions: list[HolidayOccasionOut]


class HolidayThemeAdminUpdate(BaseModel):
    """Giữ cho test cũ. Trang quản trị dùng HolidayOccasionUpdate."""

    active_theme: Optional[str] = None


class HolidayOccasionUpdate(BaseModel):
    code: str
    enabled: Optional[bool] = None
    start_month: Optional[int] = Field(None, ge=1, le=12)
    start_day: Optional[int] = Field(None, ge=1, le=31)
    end_month: Optional[int] = Field(None, ge=1, le=12)
    end_day: Optional[int] = Field(None, ge=1, le=31)
    lead_days: Optional[int] = Field(None, ge=0, le=60)
    after_days: Optional[int] = Field(None, ge=0, le=60)
    sale_percent: Optional[float] = Field(None, ge=0, le=50)

    @field_validator("code")
    @classmethod
    def known_code(cls, value: str) -> str:
        from app.services.holiday_schedule import CATALOG

        if value not in CATALOG:
            raise ValueError("Dịp lễ không có trong danh sách")
        return value


class HolidayPreviewGrantIn(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def known_code(cls, value: str) -> str:
        from app.services.holiday_schedule import CATALOG

        if value not in CATALOG:
            raise ValueError("Dịp lễ không có trong danh sách")
        return value


class HolidayPreviewGrantOut(BaseModel):
    code: str
    token: str
    expires_at: int


class HolidayPreviewCheckOut(BaseModel):
    code: str
    expires_at: int
