from typing import Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user_optional
from app.schemas.analytics import AnalyticsEventCreate, AnalyticsEventResponse
from app.crud.analytics import create_event
from app.models.user import User

router = APIRouter()


@router.post("/events", response_model=AnalyticsEventResponse)
def track_event(
    payload: AnalyticsEventCreate,
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    user_agent = request.headers.get("user-agent")
    user_id = current_user.id if current_user else None
    return create_event(db, user_id, payload, user_agent)
