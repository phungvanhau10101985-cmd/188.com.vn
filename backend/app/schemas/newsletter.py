from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr
    source: str = Field(default="footer", max_length=50)


class NewsletterSubscribeResponse(BaseModel):
    ok: bool = True
    message: str


class AdminNewsletterSubscriberOut(BaseModel):
    id: int
    email: str
    user_id: Optional[int] = None
    user_full_name: Optional[str] = None
    subscriber_name: Optional[str] = None
    gender: Optional[str] = None
    birthday: Optional[str] = None
    phone: Optional[str] = None
    email_original: Optional[str] = None
    source: str
    is_active: bool
    subscribed_at: Optional[str] = None
    unsubscribed_at: Optional[str] = None
    created_at: Optional[str] = None


class AdminNewsletterListResponse(BaseModel):
    items: list[AdminNewsletterSubscriberOut]
    total: int
    skip: int
    limit: int
    active_total: int


class AdminNewsletterImportTextRequest(BaseModel):
    emails_text: str = Field(..., min_length=1, max_length=500_000)
    source: str = Field(default="import", max_length=50)


class AdminNewsletterImportCorrectionOut(BaseModel):
    row: int
    original: str
    fixed: str
    fixes: list[str] = Field(default_factory=list)


class AdminNewsletterImportInvalidOut(BaseModel):
    row: int
    email: str
    reason: str


class AdminNewsletterImportResponse(BaseModel):
    created: int
    reactivated: int
    skipped_active: int
    updated_profile: int = 0
    invalid: int
    corrected: int = 0
    duplicate_in_file: int = 0
    total_input: int
    parsed: int
    corrections: list[AdminNewsletterImportCorrectionOut] = Field(default_factory=list)
    invalid_rows: list[AdminNewsletterImportInvalidOut] = Field(default_factory=list)


class AdminNewsletterCampaignRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=20_000)
    test_email: Optional[EmailStr] = None


class AdminNewsletterCampaignResponse(BaseModel):
    ok: bool = True
    mode: str
    recipient_count: int = 0
    sent: int = 0
    failed: int = 0
    message: str

