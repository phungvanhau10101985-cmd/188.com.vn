from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationUpdate
from datetime import datetime

def get_user_notifications(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Notification]:
    # Chỉ lấy thông báo đã đến giờ gửi (scheduled_at <= now)
    now = datetime.now()
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.scheduled_at <= now
    ).order_by(desc(Notification.created_at)).offset(skip).limit(limit).all()

def get_unread_count(db: Session, user_id: int) -> int:
    now = datetime.now()
    return db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
        Notification.scheduled_at <= now
    ).count()

def create_notification(db: Session, notification: NotificationCreate) -> Notification:
    db_obj = Notification(
        user_id=notification.user_id,
        title=notification.title,
        content=notification.content,
        type=notification.type,
        scheduled_at=notification.scheduled_at,
        expires_at=notification.expires_at
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    try:
        from app.services.push_service import send_for_notification

        send_for_notification(db, db_obj)
    except Exception:
        # Push là phụ, không fail tạo thông báo
        pass
    return db_obj

def mark_as_read(db: Session, notification_id: int, user_id: int) -> Optional[Notification]:
    notification = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user_id
    ).first()
    if notification:
        notification.is_read = True
        db.commit()
        db.refresh(notification)
    return notification

def mark_all_as_read(db: Session, user_id: int):
    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()

def delete_expired_notifications(db: Session):
    now = datetime.now()
    # Xóa các thông báo đã hết hạn
    deleted_count = db.query(Notification).filter(Notification.expires_at <= now).delete()
    db.commit()
    return deleted_count
