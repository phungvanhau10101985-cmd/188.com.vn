from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AdSpendSettingsView(BaseModel):
    google_customer_id: str = ""
    google_login_customer_id: str = ""
    google_developer_token_set: bool = False
    google_client_id_set: bool = False
    google_client_secret_set: bool = False
    google_refresh_token_set: bool = False
    google_service_account_email: str = ""
    google_configured: bool = False
    google_credential_source: str = "incomplete"
    meta_ad_account_id: str = ""
    meta_access_token_set: bool = False
    facebook_configured: bool = False
    meta_credential_source: str = "incomplete"
    google_ads_api_version: str = "v25"
    meta_graph_api_version: str = "v25.0"


class AdSpendSettingsUpdate(BaseModel):
    google_customer_id: Optional[str] = None
    google_login_customer_id: Optional[str] = None
    google_developer_token: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_refresh_token: Optional[str] = None
    meta_ad_account_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    clear_google_secrets: bool = False
    clear_meta_secrets: bool = False


class AdSpendDay(BaseModel):
    date: str
    spend: float
    impressions: int
    clicks: int


class AdSpendCampaign(BaseModel):
    id: str
    name: str
    spend: float
    impressions: int
    clicks: int


class AdSpendPlatformReport(BaseModel):
    configured: bool
    ok: bool
    error: Optional[str] = None
    currency: Optional[str] = None
    spend: float = 0
    impressions: int = 0
    clicks: int = 0
    daily: List[AdSpendDay] = Field(default_factory=list)
    campaigns: List[AdSpendCampaign] = Field(default_factory=list)
    partial: bool = False


class AdSpendReport(BaseModel):
    date_from: str
    date_to: str
    google: AdSpendPlatformReport
    facebook: AdSpendPlatformReport
    total_spend: Optional[float] = None
    total_currency: Optional[str] = None
    total_status: Literal["ok", "mixed_currency", "incomplete"] = "incomplete"
