from typing import Optional
from sqlalchemy.orm import Session
from app.models.analytics_event import AnalyticsEvent
from app.schemas.analytics import AnalyticsEventCreate


def create_event(db: Session, user_id: Optional[int], event: AnalyticsEventCreate, user_agent: Optional[str]):
    db_event = AnalyticsEvent(
        user_id=user_id,
        session_id=event.session_id,
        event_name=event.event_name,
        page_url=event.page_url,
        referrer=event.referrer,
        properties=event.properties,
        user_agent=user_agent,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event
