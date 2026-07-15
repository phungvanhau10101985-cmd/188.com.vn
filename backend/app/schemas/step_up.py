from typing import Literal, Optional

from pydantic import BaseModel, Field


class StepUpRequest(BaseModel):
    purpose: Literal["sensitive_action", "admin_elevation"] = "sensitive_action"


class StepUpVerify(BaseModel):
    challenge_id: str = Field(..., min_length=32, max_length=64)
    otp: str = Field(..., min_length=6, max_length=8)


class StepUpResponse(BaseModel):
    ok: bool = True
    challenge_id: Optional[str] = None
    expires_in_minutes: int
    message: str


class AdminOtpVerify(BaseModel):
    challenge_id: str = Field(..., min_length=32, max_length=64)
    otp: str = Field(..., min_length=6, max_length=8)
    remember_device: bool = True


class AdminStepUpResponse(BaseModel):
    ok: bool = True
    challenge_id: Optional[str] = None
    expires_in_minutes: int
    message: str
    step_up_token: Optional[str] = None
