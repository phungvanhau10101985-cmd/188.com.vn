from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.admin_permissions import admin_allowed_operation, http_method_to_admin_crud_need
from app.core.security import (
    get_current_admin,
    get_current_user_optional,
    require_module_permission,
    require_privileged_admin,
)
from app.crud import sale_calendar as crud_sale_calendar
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.user import User
from app.schemas.sale_calendar import (
    SaleCalendarMonthRuleOut,
    SaleCalendarMonthRuleUpdate,
    SaleCalendarPublicResponse,
    SaleCalendarSettingsOut,
    SaleCalendarSettingsUpdate,
)
from app.services import sale_calendar as sale_calendar_svc
from app.services.admin_feature_test_site_sale import (
    get_site_sale_test_settings_row,
    site_sale_test_settings_payload as _site_sale_test_settings_payload,
    upsert_site_sale_test_settings,
)

router = APIRouter()


def require_sale_settings_admin(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Trang Khuyến mãi và Sale lịch dùng chung API cấu hình sale site-wide."""
    op = http_method_to_admin_crud_need(request.method)
    if admin_allowed_operation(admin, db, "sale_calendar", op) or admin_allowed_operation(
        admin, db, "promotions", op
    ):
        return admin
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Không có quyền cấu hình sale site-wide (cần quyền Khuyến mãi hoặc Sale lịch).",
    )


class SiteSaleTestSettingsIn(BaseModel):
    site_sale_test_enabled: bool
    site_sale_test_phase: Literal["teaser", "active"] = "active"
    test_email: str | None = None


def _default_pct(month: int) -> float:
    return 6.0 if month % 2 == 1 else 8.0


def _build_admin_settings_out(db: Session) -> SaleCalendarSettingsOut:
    sale_calendar_svc.maintain_sale_calendar_settings(db)
    settings = crud_sale_calendar.get_settings(db)
    rules = crud_sale_calendar.list_month_rules(db)
    state = sale_calendar_svc.resolve_sale_calendar_state(db)
    month_out = [
        SaleCalendarMonthRuleOut(
            month=r.month,
            enabled=bool(r.enabled),
            discount_percent_override=(
                float(r.discount_percent_override) if r.discount_percent_override is not None else None
            ),
            default_discount_percent=_default_pct(r.month),
        )
        for r in rules
    ]
    mode = (getattr(settings, "schedule_mode", None) or "auto").strip().lower()
    if mode not in ("auto", "scheduled", "manual"):
        mode = "auto"
    scheduled_d = sale_calendar_svc.coerce_sale_date(getattr(settings, "scheduled_sale_date", None))
    manual_d = sale_calendar_svc.coerce_sale_date(getattr(settings, "manual_sale_date", None))
    return SaleCalendarSettingsOut(
        enabled=bool(settings.enabled),
        teaser_days=int(settings.teaser_days or 3),
        schedule_mode=mode,  # type: ignore[arg-type]
        scheduled_sale_date=scheduled_d.isoformat() if scheduled_d else None,
        scheduled_discount_percent=(
            float(settings.scheduled_discount_percent)
            if getattr(settings, "scheduled_discount_percent", None) is not None
            else None
        ),
        manual_sale_date=manual_d.isoformat() if manual_d else None,
        manual_discount_percent=(
            float(settings.manual_discount_percent)
            if getattr(settings, "manual_discount_percent", None) is not None
            else None
        ),
        month_rules=month_out,
        upcoming=sale_calendar_svc.list_upcoming_events(db, limit=8),
        current=SaleCalendarPublicResponse(**state.to_public_dict()),
    )


@router.get("/current", response_model=SaleCalendarPublicResponse)
def get_current_sale_calendar(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    state = sale_calendar_svc.resolve_sale_calendar_state(db, user=current_user)
    return SaleCalendarPublicResponse(**state.to_public_dict())


@router.get("/admin/test-settings")
def get_site_sale_test_settings(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    row = get_site_sale_test_settings_row(db, current_admin.id)
    return _site_sale_test_settings_payload(current_admin, row)


@router.put("/admin/test-settings")
def update_site_sale_test_settings(
    payload: SiteSaleTestSettingsIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    try:
        return upsert_site_sale_test_settings(
            db,
            current_admin,
            site_sale_test_enabled=payload.site_sale_test_enabled,
            site_sale_test_phase=payload.site_sale_test_phase,
            test_email=payload.test_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/settings", response_model=SaleCalendarSettingsOut)
def admin_get_sale_calendar_settings(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_sale_settings_admin),
):
    return _build_admin_settings_out(db)


@router.patch("/admin/settings", response_model=SaleCalendarSettingsOut)
def admin_update_sale_calendar_settings(
    payload: SaleCalendarSettingsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_sale_settings_admin),
):
    fields_set = payload.model_fields_set
    if "scheduled_sale_date" in fields_set and payload.scheduled_sale_date and not payload.clear_scheduled:
        pass
    elif payload.schedule_mode == "scheduled" and "scheduled_sale_date" in fields_set:
        if not payload.scheduled_sale_date:
            raise HTTPException(status_code=400, detail="Cần chọn ngày sale khi đặt lịch")
    if payload.schedule_mode == "manual" and "manual_sale_date" in fields_set:
        if not payload.manual_sale_date:
            raise HTTPException(status_code=400, detail="Cần chọn ngày sale khi chạy thủ công")
    crud_sale_calendar.update_settings(
        db,
        enabled=payload.enabled if "enabled" in fields_set else None,
        teaser_days=payload.teaser_days if "teaser_days" in fields_set else None,
        schedule_mode=payload.schedule_mode if "schedule_mode" in fields_set else None,
        scheduled_sale_date=payload.scheduled_sale_date if "scheduled_sale_date" in fields_set else None,
        scheduled_discount_percent=(
            payload.scheduled_discount_percent if "scheduled_discount_percent" in fields_set else None
        ),
        manual_sale_date=payload.manual_sale_date if "manual_sale_date" in fields_set else None,
        manual_discount_percent=payload.manual_discount_percent if "manual_discount_percent" in fields_set else None,
        clear_scheduled=payload.clear_scheduled,
        clear_manual=payload.clear_manual,
    )
    return _build_admin_settings_out(db)


@router.patch("/admin/month-rules", response_model=SaleCalendarMonthRuleOut)
def admin_update_month_rule(
    payload: SaleCalendarMonthRuleUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_sale_settings_admin),
):
    override: Optional[float] = payload.discount_percent_override
    clear_override = "discount_percent_override" in payload.model_fields_set and override is None
    row = crud_sale_calendar.update_month_rule(
        db,
        month=payload.month,
        enabled=payload.enabled,
        discount_percent_override=override if not clear_override else None,
        clear_override=clear_override,
    )
    return SaleCalendarMonthRuleOut(
        month=row.month,
        enabled=bool(row.enabled),
        discount_percent_override=(
            float(row.discount_percent_override) if row.discount_percent_override is not None else None
        ),
        default_discount_percent=_default_pct(row.month),
    )
