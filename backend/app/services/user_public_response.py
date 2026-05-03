"""Chuẩn hoá UserResponse cho API (quyền admin liên kết)."""
from typing import Iterable, List

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.user import UserResponse
from app.core.admin_permissions import effective_module_keys


def _linked_admin_row(db: Session, user_id: int):
    return (
        db.query(AdminUser)
        .filter(
            AdminUser.linked_user_id == user_id,
            AdminUser.is_active.is_(True),
        )
        .first()
    )


def user_response_with_linked_admin(db: Session, user: User) -> UserResponse:
    base = UserResponse.model_validate(user)
    row = _linked_admin_row(db, user.id)
    if not row:
        return base.model_copy(
            update={
                "has_linked_admin": False,
                "linked_admin_role": None,
                "linked_admin_username": None,
                "linked_admin_modules": None,
            }
        )
    rv = row.role.value if hasattr(row.role, "value") else str(row.role)
    return base.model_copy(
        update={
            "has_linked_admin": True,
            "linked_admin_role": rv,
            "linked_admin_username": row.username,
            "linked_admin_modules": effective_module_keys(row, db),
        }
    )


def admin_panel_user_response(db: Session, user: User) -> UserResponse:
    """Giống user_response_with_linked_admin — dùng cho GET/PATCH admin."""
    return user_response_with_linked_admin(db, user)


def batch_admin_panel_user_responses(db: Session, users: Iterable[User]) -> List[UserResponse]:
    user_list = list(users)
    if not user_list:
        return []
    ids = [u.id for u in user_list]
    rows = (
        db.query(AdminUser)
        .filter(
            AdminUser.linked_user_id.in_(ids),
            AdminUser.is_active.is_(True),
        )
        .all()
    )
    by_uid = {r.linked_user_id: r for r in rows}
    out: List[UserResponse] = []
    for u in user_list:
        base = UserResponse.model_validate(u)
        row = by_uid.get(u.id)
        if row:
            rv = row.role.value if hasattr(row.role, "value") else str(row.role)
            out.append(
                base.model_copy(
                    update={
                        "has_linked_admin": True,
                        "linked_admin_role": rv,
                        "linked_admin_username": row.username,
                        "linked_admin_modules": effective_module_keys(row, db),
                    }
                )
            )
        else:
            out.append(
                base.model_copy(
                    update={
                        "has_linked_admin": False,
                        "linked_admin_role": None,
                        "linked_admin_username": None,
                        "linked_admin_modules": None,
                    }
                )
            )
    return out
