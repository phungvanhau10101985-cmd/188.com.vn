from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import Optional


BIRTHDAY_DISCOUNT_PERCENT = 10
BIRTHDAY_OFFER_DAYS_BEFORE_MIN = 1
BIRTHDAY_OFFER_DAYS_BEFORE_MAX = 7
BIRTHDAY_EMAIL_SEND_DAYS_BEFORE = 7


@dataclass(frozen=True)
class BirthdayDiscount:
    active: bool
    percent: int
    days_until: Optional[int]
    next_birthday: Optional[date]


def _next_birthday_for(dob: date, today: date) -> date:
    year = today.year
    month = dob.month
    day = dob.day
    while True:
        try:
            candidate = date(year, month, day)
        except ValueError:
            # 29/02 được ưu đãi vào 28/02 ở năm không nhuận.
            candidate = date(year, 2, 28)
        if candidate >= today:
            return candidate
        year += 1


def get_birthday_discount(dob: Optional[date], today: Optional[date] = None) -> BirthdayDiscount:
    if dob is None:
        return BirthdayDiscount(False, 0, None, None)

    current_day = today or date.today()
    next_birthday = _next_birthday_for(dob, current_day)
    days_until = (next_birthday - current_day).days
    min_days = min(BIRTHDAY_OFFER_DAYS_BEFORE_MIN, BIRTHDAY_OFFER_DAYS_BEFORE_MAX)
    max_days = max(BIRTHDAY_OFFER_DAYS_BEFORE_MIN, BIRTHDAY_OFFER_DAYS_BEFORE_MAX)
    active = days_until == 0 or min_days <= days_until <= max_days

    return BirthdayDiscount(
        active=active,
        percent=BIRTHDAY_DISCOUNT_PERCENT if active else 0,
        days_until=days_until,
        next_birthday=next_birthday,
    )


def birthday_campaign_key(next_birthday: date) -> str:
    return f"bday_{next_birthday.strftime('%Y%m%d')}"


def is_birthday_promo_test_enabled(db, user) -> bool:
    user_id = getattr(user, "id", None)
    user_email = (getattr(user, "email", None) or "").strip().lower()
    if not user_id and not user_email:
        return False
    try:
        from sqlalchemy import func, or_

        from app.models.admin import AdminUser
        from app.models.admin_feature_test import AdminFeatureTestSetting

        row = (
            db.query(AdminFeatureTestSetting)
            .join(AdminUser, AdminUser.id == AdminFeatureTestSetting.admin_id)
            .filter(
                or_(
                    func.lower(AdminFeatureTestSetting.test_email) == user_email,
                    AdminUser.linked_user_id == user_id,
                )
            )
            .filter(AdminUser.is_active == True)  # noqa: E712
            .filter(AdminFeatureTestSetting.birthday_promo_enabled == True)  # noqa: E712
            .filter(AdminFeatureTestSetting.birthday_promo_expires_at.isnot(None))
            .filter(AdminFeatureTestSetting.birthday_promo_expires_at > datetime.now(timezone.utc))
            .first()
        )
        return row is not None
    except Exception:
        return False


def get_birthday_discount_for_user(db, user, today: Optional[date] = None) -> BirthdayDiscount:
    discount = get_birthday_discount(getattr(user, "date_of_birth", None), today=today)
    if discount.active:
        return discount

    if is_birthday_promo_test_enabled(db, user):
        current_day = today or date.today()
        return BirthdayDiscount(
            active=True,
            percent=BIRTHDAY_DISCOUNT_PERCENT,
            days_until=BIRTHDAY_EMAIL_SEND_DAYS_BEFORE,
            next_birthday=current_day + timedelta(days=BIRTHDAY_EMAIL_SEND_DAYS_BEFORE),
        )

    return discount
