"""Xóa tài khoản admin nhân viên đã gỡ quyền (không còn liên kết / không active)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.admin import AdminUser, AdminRole


def staff_admin_delete_block_reason(
    current_admin: AdminUser,
    target: AdminUser,
) -> Optional[str]:
    """Trả về thông báo lỗi nếu không được xóa; None nếu được phép."""
    if target.id == current_admin.id:
        return "Không thể xóa tài khoản đang đăng nhập."
    if target.role == AdminRole.SUPER_ADMIN:
        return "Không thể xóa super_admin."
    if target.is_active:
        return "Chỉ xóa được tài khoản đã vô hiệu hóa — gỡ «Quản trị web» ở Thành viên trước."
    if target.linked_user_id is not None:
        return "Tài khoản còn liên kết thành viên — đặt «Quản trị web» = Không ở Thành viên trước."
    return None


def remove_linked_staff_admin_row(db: Session, row: AdminUser) -> None:
    """Gỡ quyền qua thành viên — xóa hẳn bản ghi admin (trừ super_admin)."""
    if row.role == AdminRole.SUPER_ADMIN:
        raise ValueError("Không thể gỡ liên kết tài khoản super_admin.")
    db.delete(row)


def delete_staff_admin_account(
    db: Session,
    current_admin: AdminUser,
    target: AdminUser,
) -> None:
    reason = staff_admin_delete_block_reason(current_admin, target)
    if reason:
        raise ValueError(reason)
    db.delete(target)
    db.commit()
