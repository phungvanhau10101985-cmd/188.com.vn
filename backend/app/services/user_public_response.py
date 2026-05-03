"""Chuẩn hoá UserResponse cho API công khai (cờ quyền admin liên kết)."""
from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.user import UserResponse


def user_response_with_linked_admin(db: Session, user: User) -> UserResponse:
    base = UserResponse.model_validate(user)
    linked = (
        db.query(AdminUser.id)
        .filter(
            AdminUser.linked_user_id == user.id,
            AdminUser.is_active.is_(True),
        )
        .first()
    )
    return base.model_copy(update={"has_linked_admin": linked is not None})
