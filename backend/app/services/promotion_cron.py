from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.services import promotion_grants as grant_svc
from app.services.birthday_promo_jobs import run_birthday_promo_email_batch


def run_daily_voucher_grants(
    db: Session,
    *,
    inactive_days: int = 30,
    abandon_hours: int = 24,
    include_welcome_backfill: bool = True,
) -> Dict[str, Any]:
    grant_svc.ensure_promotion_templates(db)
    result: Dict[str, Any] = {
        "cart_abandon": grant_svc.process_cart_abandon_grants_for_all(
            db,
            abandon_hours=abandon_hours,
        ),
        "comeback": grant_svc.process_comeback_grants_for_all(
            db,
            inactive_days=inactive_days,
        ),
    }
    if include_welcome_backfill:
        result["welcome_backfill"] = grant_svc.process_welcome_backfill(db)
    return result


def run_daily_promotion_cron(
    db: Session,
    *,
    inactive_days: int = 30,
    abandon_hours: int = 24,
    include_welcome_backfill: bool = True,
    include_birthday_emails: bool = True,
) -> Dict[str, Any]:
    """Cron gộp: tặng mã ví (cart/comeback/backfill) + email CMSN."""
    out: Dict[str, Any] = {
        "voucher_grants": run_daily_voucher_grants(
            db,
            inactive_days=inactive_days,
            abandon_hours=abandon_hours,
            include_welcome_backfill=include_welcome_backfill,
        ),
    }
    if include_birthday_emails:
        out["birthday_emails"] = run_birthday_promo_email_batch(db)
    return out
