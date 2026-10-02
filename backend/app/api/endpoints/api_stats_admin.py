"""Admin — thống kê chi phí API các model AI."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.services.ai_usage_report import build_api_usage_report

router = APIRouter()


@router.get("/report")
def get_api_stats_report(
    date_from: str = Query(..., description="YYYY-MM-DD, giờ Việt Nam"),
    date_to: str = Query(..., description="YYYY-MM-DD, giờ Việt Nam"),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    try:
        return build_api_usage_report(db, date_from, date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Khoảng ngày không hợp lệ.") from exc
