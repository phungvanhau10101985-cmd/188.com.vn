from pydantic import BaseModel, Field


class EmailWarmupSettingsIn(BaseModel):
    warmup_enabled: bool
    start_limit: int = Field(default=5, ge=1, le=100_000)
    daily_increment: int = Field(default=5, ge=1, le=10_000)
    max_limit: int | None = Field(default=None, ge=1, le=1_000_000)
    birthday_cron_enabled: bool = True


class EmailSendDailyHistoryItem(BaseModel):
    date: str
    birthday_sent: int


class EmailSendManagementOut(BaseModel):
    warmup_enabled: bool
    start_limit: int
    daily_increment: int
    max_limit: int | None
    birthday_cron_enabled: bool
    warmup_day: int
    warmup_started_at: str | None
    daily_limit: int | None
    daily_sent_total: int
    daily_birthday_sent: int
    daily_marketing_sent: int
    remaining_today: int | None
    birthday_pending_today: int
    birthday_sent_all_time: int
    birthday_send_days_before: int
    recent_days: list[EmailSendDailyHistoryItem]
