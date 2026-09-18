from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user_optional, require_module_permission
from app.db.session import SessionLocal, get_db
from app.models.admin import AdminUser
from app.models.marketing_icon import MarketingIconAsset
from app.models.user import User
from app.schemas.marketing_icon import (
    MarketingIconAdminItem,
    MarketingIconAdminListResponse,
    MarketingIconCurrentResponse,
    MarketingIconRegenerateRequest,
)
from app.services import marketing_icon as icon_svc
from app.services import sale_calendar as sale_svc

router = APIRouter()


@router.get("/current", response_model=MarketingIconCurrentResponse)
def current_marketing_icon(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    return MarketingIconCurrentResponse(**icon_svc.current_sale_icon_state(db, user=current_user))


def _admin_item(row: MarketingIconAsset) -> MarketingIconAdminItem:
    return MarketingIconAdminItem(**icon_svc.serialize_asset(row))


@router.get("/admin/assets", response_model=MarketingIconAdminListResponse)
def admin_list_icon_assets(
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="view")),
):
    rows = (
        db.query(MarketingIconAsset)
        .order_by(MarketingIconAsset.created_at.desc(), MarketingIconAsset.id.desc())
        .limit(limit)
        .all()
    )
    return MarketingIconAdminListResponse(items=[_admin_item(row) for row in rows])


def _sale_percent_for_date(db: Session, day: int, month: int) -> float:
    if day != month:
        raise ValueError("Icon sale chỉ áp dụng cho ngày trùng tháng.")
    for event in sale_svc.list_upcoming_events(db, limit=24):
        event_date = date.fromisoformat(str(event["event_date"])[:10])
        if event_date.day == day and event_date.month == month:
            return float(event["discount_percent"])
    raise ValueError("Không tìm thấy campaign sale sắp tới cho ngày này.")


def _generate_in_background(day: int, month: int, discount: float) -> None:
    db = SessionLocal()
    try:
        icon_svc.generate_sale_icon(
            db,
            day=day,
            month=month,
            discount_percent=discount,
            force=True,
            notify_admin=True,
        )
    finally:
        db.close()


@router.post("/admin/regenerate", status_code=202)
def admin_regenerate_icon(
    payload: MarketingIconRegenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="update")),
):
    try:
        date(2000, payload.month, payload.day)
        discount = _sale_percent_for_date(db, payload.day, payload.month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    key = icon_svc.campaign_key("sale", payload.day, payload.month, discount)
    active_generation = (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == "sale",
            MarketingIconAsset.campaign_key == key,
            MarketingIconAsset.status == "generating",
        )
        .first()
    )
    if active_generation:
        raise HTTPException(status_code=409, detail="Icon này đang được tạo.")

    background_tasks.add_task(_generate_in_background, payload.day, payload.month, discount)
    return {"accepted": True, "message": "Đã bắt đầu tạo favicon / ảnh đại diện sale."}


@router.post("/admin/assets/{asset_id}/activate")
def admin_activate_icon_version(
    asset_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="update")),
):
    row = db.query(MarketingIconAsset).filter(MarketingIconAsset.id == asset_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy icon.")
    if row.status != "ready" or not row.image_url:
        raise HTTPException(status_code=400, detail="Chỉ có thể kích hoạt ảnh đã tạo thành công.")
    (
        db.query(MarketingIconAsset)
        .filter(
            MarketingIconAsset.kind == row.kind,
            MarketingIconAsset.campaign_key == row.campaign_key,
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    row.is_active = True
    db.commit()
    db.refresh(row)
    return _admin_item(row)
