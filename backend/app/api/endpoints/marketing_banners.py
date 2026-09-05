from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import get_current_user_optional, require_module_permission
from app.db.session import SessionLocal, get_db
from app.models.admin import AdminUser
from app.models.marketing_banner import MarketingBannerAsset
from app.models.user import User
from app.schemas.marketing_banner import (
    MarketingBannerAdminItem,
    MarketingBannerAdminListResponse,
    MarketingBannerCurrentResponse,
    MarketingBannerItem,
    MarketingBannerRegenerateRequest,
)
from app.services import marketing_banner as banner_svc
from app.services import sale_calendar as sale_svc
from app.services.birthday_discount import (
    BIRTHDAY_DISCOUNT_PERCENT,
    get_birthday_discount_for_user,
)

router = APIRouter()


def _public_item(
    row: MarketingBannerAsset,
    *,
    event_date: str | None = None,
    greeting: str | None = None,
) -> MarketingBannerItem:
    return MarketingBannerItem(
        id=row.id,
        kind=row.kind,
        campaign_key=row.campaign_key,
        date_key=row.date_key,
        discount_percent=float(row.discount_percent),
        image_url=row.image_url or "",
        aspect_ratio=row.aspect_ratio,
        event_date=event_date,
        greeting=greeting,
        version=row.version,
    )


@router.get("/current", response_model=MarketingBannerCurrentResponse)
def current_marketing_banners(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    items: list[MarketingBannerItem] = []

    if current_user is not None:
        birthday = get_birthday_discount_for_user(db, current_user)
        if birthday.active and birthday.next_birthday:
            birthday_asset = banner_svc.find_active_asset(
                db,
                kind="birthday",
                day=birthday.next_birthday.day,
                month=birthday.next_birthday.month,
                discount_percent=birthday.percent,
            )
            if birthday_asset and birthday_asset.image_url:
                display_name = (current_user.full_name or "Quý khách").strip()
                greeting = f"Món quà sinh nhật dành riêng cho {display_name}"
                items.append(
                    _public_item(
                        birthday_asset,
                        event_date=birthday.next_birthday.isoformat(),
                        greeting=greeting,
                    )
                )

    sale = sale_svc.resolve_sale_calendar_state(db, user=current_user)
    if sale.phase and sale.event_date and sale.event_date.day == sale.event_date.month:
        sale_asset = banner_svc.find_active_asset(
            db,
            kind="sale",
            day=sale.event_date.day,
            month=sale.event_date.month,
            discount_percent=sale.discount_percent,
        )
        if sale_asset and sale_asset.image_url:
            items.append(
                _public_item(sale_asset, event_date=sale.event_date.isoformat())
            )
    return MarketingBannerCurrentResponse(items=items)


def _admin_item(row: MarketingBannerAsset) -> MarketingBannerAdminItem:
    return MarketingBannerAdminItem(**banner_svc.serialize_asset(row))


@router.get("/admin/assets", response_model=MarketingBannerAdminListResponse)
def admin_list_banner_assets(
    kind: str | None = Query(default=None, pattern="^(sale|birthday)$"),
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="view")),
):
    query = db.query(MarketingBannerAsset)
    if kind:
        query = query.filter(MarketingBannerAsset.kind == kind)
    rows = (
        query.order_by(
            MarketingBannerAsset.created_at.desc(),
            MarketingBannerAsset.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return MarketingBannerAdminListResponse(items=[_admin_item(row) for row in rows])


def _sale_percent_for_date(db: Session, day: int, month: int) -> float:
    if day != month:
        raise ValueError("Banner sale chỉ áp dụng cho ngày trùng tháng.")
    for event in sale_svc.list_upcoming_events(db, limit=24):
        event_date = date.fromisoformat(str(event["event_date"])[:10])
        if event_date.day == day and event_date.month == month:
            return float(event["discount_percent"])
    raise ValueError("Không tìm thấy campaign sale sắp tới cho ngày này.")


def _generate_in_background(kind: str, day: int, month: int, discount: float) -> None:
    db = SessionLocal()
    try:
        banner_svc.generate_banner(
            db,
            kind=kind,
            day=day,
            month=month,
            discount_percent=discount,
            force=True,
            notify_admin=True,
        )
    finally:
        db.close()


@router.post("/admin/regenerate", status_code=202)
def admin_regenerate_banner(
    payload: MarketingBannerRegenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="update")),
):
    try:
        date(2000, payload.month, payload.day)
        discount = (
            float(BIRTHDAY_DISCOUNT_PERCENT)
            if payload.kind == "birthday"
            else _sale_percent_for_date(db, payload.day, payload.month)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active_generation = (
        db.query(MarketingBannerAsset)
        .filter(
            MarketingBannerAsset.kind == payload.kind,
            MarketingBannerAsset.campaign_key
            == banner_svc.campaign_key(
                payload.kind,
                payload.day,
                payload.month,
                discount,
            ),
            MarketingBannerAsset.status == "generating",
        )
        .first()
    )
    if active_generation:
        raise HTTPException(status_code=409, detail="Banner này đang được tạo.")

    background_tasks.add_task(
        _generate_in_background,
        payload.kind,
        payload.day,
        payload.month,
        discount,
    )
    return {"accepted": True, "message": "Đã bắt đầu tạo lại banner."}


@router.post("/admin/assets/{asset_id}/activate")
def admin_activate_banner_version(
    asset_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("promotions", need="update")),
):
    row = (
        db.query(MarketingBannerAsset)
        .filter(MarketingBannerAsset.id == asset_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy banner.")
    if row.status != "ready" or not row.image_url:
        raise HTTPException(status_code=400, detail="Chỉ có thể kích hoạt ảnh đã tạo thành công.")
    (
        db.query(MarketingBannerAsset)
        .filter(
            MarketingBannerAsset.kind == row.kind,
            MarketingBannerAsset.campaign_key == row.campaign_key,
        )
        .update({"is_active": False}, synchronize_session=False)
    )
    row.is_active = True
    db.commit()
    db.refresh(row)
    return _admin_item(row)
