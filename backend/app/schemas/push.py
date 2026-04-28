from typing import Optional

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=8)
    keys: PushKeys
    user_agent: Optional[str] = None


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(..., min_length=8)


class VapidPublicOut(BaseModel):
    public_key: str


class OkOut(BaseModel):
    ok: bool
    message: Optional[str] = None
