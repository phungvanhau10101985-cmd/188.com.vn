from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user_optional, require_module_permission, require_privileged_admin
from app.crud import sale_calendar as crud_sale_calendar
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.admin_feature_test import AdminFeatureTestSetting
from app.models.user import User
from app.schemas.sale_calendar import (
    SaleCalendarMonthRuleOut,
    SaleCalendarMonthRuleUpdate,
    SaleCalendarPublicResponse,
    SaleCalendarSettingsOut,
    SaleCalendarSettingsUpdate,
)
from app.services import sale_calendar as sale_calendar_svc
from app.utils.display_timeline import to_utc_aware

router = APIRouter()
TEST_DURATION_MINUTES = sale_calendar_svc.SITE_SALE_TEST_DURATION_MINUTES


class SiteSaleTestSettingsIn(BaseModel):
    site_sale_test_enabled: bool
    site_sale_test_phase: Literal["teaser", "active"] = "active"
    test_email: str | None = None


def _site_sale_test_settings_payload(admin: AdminUser, row: AdminFeatureTestSetting | None) -> dict:
    test_email = ((row.test_email if row else None) or admin.email or "").strip()
    expires_at = row.site_sale_test_expires_at if row else None
    expires_at_utc = to_utc_aware(expires_at)
    is_enabled = bool(row.site_sale_test_enabled) if row else False
    if is_enabled and (not expires_at_utc or expires_at_utc <= datetime.now(timezone.utc)):
        is_enabled = False
    phase = (getattr(row, "site_sale_test_phase", None) or "active") if row else "active"
    if phase not in ("teaser", "active"):
        phase = "active"
    return {
        "site_sale_test_enabled": is_enabled,
        "site_sale_test_expires_at": expires_at.isoformat() if expires_at else None,
        "site_sale_test_phase": phase,
        "test_duration_minutes": TEST_DURATION_MINUTES,
        "admin_email": admin.email,
        "test_email": test_email,
        "linked_user_id": admin.linked_user_id,
        "can_apply_on_web": bool(test_email),
    }


def _default_pct(month: int) -> float:
    return 6.0 if month % 2 == 1 else 8.0


def _build_admin_settings_out(db: Session) -> SaleCalendarSettingsOut:
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
    return SaleCalendarSettingsOut(
        enabled=bool(settings.enabled),
        teaser_days=int(settings.teaser_days or 3),
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
    row = (
        db.query(AdminFeatureTestSetting)
        .filter(AdminFeatureTestSetting.admin_id == current_admin.id)
        .first()
    )
    return _site_sale_test_settings_payload(current_admin, row)


@router.put("/admin/test-settings")
def update_site_sale_test_settings(
    payload: SiteSaleTestSettingsIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    row = (
        db.query(AdminFeatureTestSetting)
        .filter(AdminFeatureTestSetting.admin_id == current_admin.id)
        .first()
    )
    if not row:
        row = AdminFeatureTestSetting(admin_id=current_admin.id)
        db.add(row)
    test_email = (payload.test_email or row.test_email or current_admin.email or "").strip().lower()
    if payload.site_sale_test_enabled and not test_email:
        raise HTTPException(status_code=400, detail="Vui lòng nhập email tài khoản test.")
    row.test_email = test_email or None
    row.site_sale_test_enabled = bool(payload.site_sale_test_enabled)
    row.site_sale_test_phase = payload.site_sale_test_phase
    row.site_sale_test_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=TEST_DURATION_MINUTES)
        if payload.site_sale_test_enabled
        else None
    )
    db.commit()
    db.refresh(row)
    return _site_sale_test_settings_payload(current_admin, row)


@router.get("/admin/settings", response_model=SaleCalendarSettingsOut)
def admin_get_sale_calendar_settings(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("sale_calendar")),
):
    return _build_admin_settings_out(db)


@router.patch("/admin/settings", response_model=SaleCalendarSettingsOut)
def admin_update_sale_calendar_settings(
    payload: SaleCalendarSettingsUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("sale_calendar")),
):
    crud_sale_calendar.update_settings(
        db,
        enabled=payload.enabled,
        teaser_days=payload.teaser_days,
    )
    return _build_admin_settings_out(db)


@router.patch("/admin/month-rules", response_model=SaleCalendarMonthRuleOut)
def admin_update_month_rule(
    payload: SaleCalendarMonthRuleUpdate,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_module_permission("sale_calendar")),
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
