"""Admin — upload Bunny Storage (response JSON)."""

from pydantic import BaseModel, Field


class BunnyCdnStatusOut(BaseModel):
    configured: bool
    cdn_public_base: str = ""
    upload_path_prefix: str = ""


class BunnyCdnUploadOut(BaseModel):
    public_url: str
    remote_path: str
    bytes: int = Field(..., ge=0)
