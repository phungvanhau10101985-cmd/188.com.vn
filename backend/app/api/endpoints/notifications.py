from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import get_current_user, get_current_admin
from app.models.user import User
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, NotificationImportResponse, NotificationCreate
from app.crud import notification as crud_notification
from app.crud import user as crud_user
import pandas as pd
from datetime import datetime, timedelta
import io

router = APIRouter()

@router.get("", response_model=List[NotificationResponse], include_in_schema=False)
@router.get("/", response_model=List[NotificationResponse])
def get_my_notifications(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Tự động xóa thông báo hết hạn mỗi khi user lấy danh sách
    crud_notification.delete_expired_notifications(db)
    return crud_notification.get_user_notifications(db, user_id=current_user.id, skip=skip, limit=limit)

@router.get("/unread-count", response_model=int)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return crud_notification.get_unread_count(db, user_id=current_user.id)

@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    notification = crud_notification.mark_as_read(db, notification_id, current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification

@router.put("/read-all")
def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    crud_notification.mark_all_as_read(db, current_user.id)
    return {"message": "All marked as read"}

@router.post("/import", response_model=NotificationImportResponse)
async def import_notifications(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin)
):
    if not file.filename.endswith(('.xlsx', '.xls', '.csv')):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload Excel or CSV file.")

    contents = await file.read()
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    # Chuẩn hóa tên cột (bỏ khoảng trắng thừa, lowercase)
    df.columns = df.columns.str.strip().str.lower()
    
    # Mapping cột tiếng Việt sang tiếng Anh nếu cần
    column_mapping = {
        'số điện thoại': 'phone',
        'tiêu đề': 'title',
        'nội dung': 'content',
        'thời điểm sẽ gửi': 'time_will_send'
    }
    df.rename(columns=column_mapping, inplace=True)

    required_columns = ['phone', 'title', 'content', 'time_will_send']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(missing_columns)}")

    success_count = 0
    error_count = 0
    errors = []

    for index, row in df.iterrows():
        phone = str(row['phone']).strip()
        # Xử lý số điện thoại (bỏ .0 nếu là float)
        if phone.endswith('.0'):
            phone = phone[:-2]
            
        title = str(row['title']).strip()
        content = str(row['content']).strip()
        time_str = str(row['time_will_send']).strip()

        # Tìm user theo phone
        user = crud_user.get_user_by_phone(db, phone=phone)
        if not user:
            error_count += 1
            errors.append(f"Row {index + 2}: User with phone {phone} not found")
            continue

        # Parse thời gian
        try:
            # Hỗ trợ nhiều định dạng ngày tháng
            scheduled_at = pd.to_datetime(time_str, dayfirst=True).to_pydatetime()
        except Exception:
            error_count += 1
            errors.append(f"Row {index + 2}: Invalid date format for {time_str}")
            continue

        # Tính thời gian hết hạn (15 ngày sau khi gửi)
        expires_at = scheduled_at + timedelta(days=15)

        # Tạo notification
        notif_create = NotificationCreate(
            user_id=user.id,
            title=title,
            content=content,
            type="system",
            scheduled_at=scheduled_at,
            expires_at=expires_at
        )
        crud_notification.create_notification(db, notif_create)
        success_count += 1

    return NotificationImportResponse(
        total_processed=len(df),
        success_count=success_count,
        error_count=error_count,
        errors=errors
    )
