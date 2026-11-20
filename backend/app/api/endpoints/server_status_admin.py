"""Trạng thái máy cho trang quản trị. Tính một lần mỗi request."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.services.server_status_snapshot import build_server_status

router = APIRouter()


@router.get("")
def get_server_status(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    return build_server_status(db)
