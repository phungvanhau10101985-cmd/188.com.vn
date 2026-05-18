from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.admin_feature_test import AdminFeatureTestSetting
from app.models.birthday_promo import BirthdayPromoEmailLog
from app.models.user import User
from app.services.birthday_discount import (
    BIRTHDAY_EMAIL_SEND_DAYS_BEFORE,
    birthday_campaign_key,
    get_birthday_discount,
    get_birthday_discount_for_user,
)
from app.services.email_service import send_birthday_promo_email
from app.utils.display_timeline import to_utc_aware


router = APIRouter()
TEST_DURATION_MINUTES = 10


class BirthdayPromoTestSettingsIn(BaseModel):
    birthday_promo_enabled: bool
    test_email: str | None = None


def _require_cron_secret(authorization: str | None) -> None:
    expected = (settings.BIRTHDAY_PROMO_CRON_SECRET or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="BIRTHDAY_PROMO_CRON_SECRET is not configured")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _test_settings_payload(admin: AdminUser, row: AdminFeatureTestSetting | None) -> dict:
    test_email = ((row.test_email if row else None) or admin.email or "").strip()
    expires_at = row.birthday_promo_expires_at if row else None
    expires_at_utc = to_utc_aware(expires_at)
    is_enabled = bool(row.birthday_promo_enabled) if row else False
    if is_enabled and (
        not expires_at_utc or expires_at_utc <= datetime.now(timezone.utc)
    ):
        is_enabled = False
    return {
        "birthday_promo_enabled": is_enabled,
        "birthday_promo_expires_at": expires_at.isoformat() if expires_at else None,
        "test_duration_minutes": TEST_DURATION_MINUTES,
        "admin_email": admin.email,
        "test_email": test_email,
        "linked_user_id": admin.linked_user_id,
        "can_apply_on_web": bool(test_email),
    }


@router.get("/admin/test-settings")
def get_birthday_promo_test_settings(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    row = (
        db.query(AdminFeatureTestSetting)
        .filter(AdminFeatureTestSetting.admin_id == current_admin.id)
        .first()
    )
    return _test_settings_payload(current_admin, row)


@router.get("/me")
def get_my_birthday_promo_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    promo = get_birthday_discount_for_user(db, current_user)
    return {
        "active": promo.active,
        "percent": promo.percent,
        "days_until": promo.days_until,
        "next_birthday": promo.next_birthday.isoformat() if promo.next_birthday else None,
    }


@router.put("/admin/test-settings")
def update_birthday_promo_test_settings(
    payload: BirthdayPromoTestSettingsIn,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(require_privileged_admin),
):
    was_enabled = False
    row = (
        db.query(AdminFeatureTestSetting)
        .filter(AdminFeatureTestSetting.admin_id == current_admin.id)
        .first()
    )
    if not row:
        row = AdminFeatureTestSetting(admin_id=current_admin.id)
        db.add(row)
    else:
        was_enabled = bool(row.birthday_promo_enabled)
    test_email = (payload.test_email or current_admin.email or "").strip().lower()
    if payload.birthday_promo_enabled and not test_email:
        raise HTTPException(status_code=400, detail="Vui lòng nhập email tài khoản test.")
    row.test_email = test_email or None
    row.birthday_promo_enabled = bool(payload.birthday_promo_enabled)
    row.birthday_promo_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=TEST_DURATION_MINUTES)
        if payload.birthday_promo_enabled
        else None
    )
    db.commit()
    db.refresh(row)
    out = _test_settings_payload(current_admin, row)
    out["test_email_sent"] = False
    out["test_email_error"] = None

    if row.birthday_promo_enabled and not was_enabled:
        email = (row.test_email or current_admin.email or "").strip()
        if email:
            try:
                today = date.today()
                send_birthday_promo_email(
                    email,
                    current_admin.full_name or current_admin.username or "Tài khoản test",
                    10,
                    today.isoformat(),
                    settings.FRONTEND_BASE_URL,
                )
                out["test_email_sent"] = True
            except Exception as exc:
                out["test_email_error"] = str(exc)

    return out


@router.get("/cron/send-emails")
def send_birthday_promo_emails(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """
    Gửi email CMSN đúng 7 ngày trước sinh nhật. Log theo user + campaign_key để không gửi trùng.
    """
    _require_cron_secret(authorization)

    today = date.today()
    users = (
        db.query(User)
        .filter(User.is_active == True)  # noqa: E712
        .filter(User.email.isnot(None))
        .filter(User.email != "")
        .filter(User.date_of_birth.isnot(None))
        .all()
    )

    checked = sent = skipped = failed = 0
    failures: list[dict[str, str]] = []

    for user in users:
        checked += 1
        promo = get_birthday_discount(user.date_of_birth, today=today)
        if promo.days_until != BIRTHDAY_EMAIL_SEND_DAYS_BEFORE or not promo.next_birthday:
            continue

        campaign_key = birthday_campaign_key(promo.next_birthday)
        exists = (
            db.query(BirthdayPromoEmailLog)
            .filter(
                BirthdayPromoEmailLog.user_id == user.id,
                BirthdayPromoEmailLog.campaign_key == campaign_key,
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        email = (user.email or "").strip()
        try:
            send_birthday_promo_email(
                email,
                user.full_name or "",
                promo.percent,
                promo.next_birthday.isoformat(),
                settings.FRONTEND_BASE_URL,
            )
            db.add(
                BirthdayPromoEmailLog(
                    user_id=user.id,
                    campaign_key=campaign_key,
                    birthday_date=promo.next_birthday,
                    recipient_email=email,
                )
            )
            db.commit()
            sent += 1
        except Exception as exc:
            db.rollback()
            failed += 1
            failures.append({"user_id": str(user.id), "error": str(exc)})

    return {
        "ok": failed == 0,
        "checked": checked,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "failures": failures[:20],
    }
