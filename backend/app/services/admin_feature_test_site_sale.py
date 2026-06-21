from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.admin import AdminUser
from app.models.admin_feature_test import AdminFeatureTestSetting
from app.services import sale_calendar as sale_calendar_svc
from app.utils.display_timeline import db_datetime_to_utc

TEST_DURATION_MINUTES = sale_calendar_svc.SITE_SALE_TEST_DURATION_MINUTES


def site_sale_test_settings_payload(admin: AdminUser, row: AdminFeatureTestSetting | None) -> dict:
    test_email = ((row.test_email if row else None) or admin.email or "").strip()
    expires_at = row.site_sale_test_expires_at if row else None
    expires_at_utc = db_datetime_to_utc(expires_at)
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


def get_site_sale_test_settings_row(db: Session, admin_id: int) -> AdminFeatureTestSetting | None:
    return (
        db.query(AdminFeatureTestSetting)
        .filter(AdminFeatureTestSetting.admin_id == admin_id)
        .first()
    )


def upsert_site_sale_test_settings(
    db: Session,
    admin: AdminUser,
    *,
    site_sale_test_enabled: bool,
    site_sale_test_phase: str,
    test_email: str | None,
) -> dict:
    row = get_site_sale_test_settings_row(db, admin.id)
    if not row:
        row = AdminFeatureTestSetting(admin_id=admin.id)
        db.add(row)

    email = (test_email or row.test_email or admin.email or "").strip().lower()
    if site_sale_test_enabled and not email:
        raise ValueError("Vui lòng nhập email tài khoản test.")

    row.test_email = email or None
    row.site_sale_test_enabled = bool(site_sale_test_enabled)
    row.site_sale_test_phase = site_sale_test_phase if site_sale_test_phase in ("teaser", "active") else "active"
    row.site_sale_test_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=TEST_DURATION_MINUTES)
        if site_sale_test_enabled
        else None
    )
    db.commit()
    db.refresh(row)
    return site_sale_test_settings_payload(admin, row)
