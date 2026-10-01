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


class AdSpendProfitLine(BaseModel):
    quantity: int
    unit_price_vnd: float
    line_total_vnd: float = 0
    catalog_cny: Optional[float] = None
    import_cny: Optional[float] = None
    import_vnd: Optional[float] = None


class AdSpendProfitOrder(BaseModel):
    order_id: int
    order_code: str
    deposited_on: Optional[str] = None
    revenue_vnd: float
    merchandise_vnd: float = 0
    catalog_goods_cny: Optional[float] = None
    goods_vnd: float = 0
    uses_china_ship: bool = True
    import_stored: bool = False
    lines: List[AdSpendProfitLine] = Field(default_factory=list)
    goods_cny_override: Optional[float] = None
    ship_china_domestic_cny_override: Optional[float] = None
    ship_border_to_hanoi_cny_override: Optional[float] = None
    ship_hanoi_to_customer_vnd_override: Optional[float] = None
    cost_vnd: Optional[float] = None
    gross_profit_vnd: Optional[float] = None


class AdSpendProfitSheet(BaseModel):
    date_from: str
    date_to: str
    vnd_per_cny: float
    vnd_per_cny_saved: bool = False
    ship_china_domestic_cny: float = 0
    ship_border_to_hanoi_cny: float = 0
    ship_hanoi_to_customer_vnd: float = 0
    order_count: int = 0
    truncated: bool = False
    missing_goods_count: int = 0
    revenue_vnd: float = 0
    revenue_cny: Optional[float] = None
    cost_vnd: Optional[float] = None
    orders: List[AdSpendProfitOrder] = Field(default_factory=list)


class AdSpendProfitOrderInput(BaseModel):
    order_id: int
    goods_cny: Optional[float] = None
    ship_china_domestic_cny: Optional[float] = None
    ship_border_to_hanoi_cny: Optional[float] = None
    ship_hanoi_to_customer_vnd: Optional[float] = None


class AdSpendProfitInputsUpdate(BaseModel):
    date_from: str
    date_to: str
    vnd_per_cny: float
    ship_china_domestic_cny: float = 0
    ship_border_to_hanoi_cny: float = 0
    ship_hanoi_to_customer_vnd: float = 0
    orders: List[AdSpendProfitOrderInput] = Field(default_factory=list)
