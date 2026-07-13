from pydantic import BaseModel, Field


class MarketingUnsubscribeRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=512)


class MarketingUnsubscribeResponse(BaseModel):
    ok: bool = True
    message: str
    email_masked: str = ""
    already_unsubscribed: bool = False
