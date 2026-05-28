from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Literal, Optional

from sqlalchemy.orm import Session

from app.models.sale_calendar import SaleCalendarMonthRule, SaleCalendarSettings
from app.services import sale_calendar as sale_calendar_svc

ScheduleMode = Literal["auto", "scheduled", "manual"]


def _parse_optional_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(str(value).strip()[:10])


def get_settings(db: Session) -> SaleCalendarSettings:
    try:
        sale_calendar_svc.ensure_sale_calendar_defaults(db)
    except Exception:
        db.rollback()
        raise
    row = db.query(SaleCalendarSettings).filter(SaleCalendarSettings.id == 1).first()
    if not row:
        raise RuntimeError("sale_calendar_settings chưa được khởi tạo — chạy migration backend")
    return row


def update_settings(
    db: Session,
    *,
    enabled: Optional[bool] = None,
    teaser_days: Optional[int] = None,
    schedule_mode: Optional[ScheduleMode] = None,
    scheduled_sale_date: Optional[str] = None,
    scheduled_discount_percent: Optional[float] = None,
    manual_sale_date: Optional[str] = None,
    manual_discount_percent: Optional[float] = None,
    clear_scheduled: bool = False,
    clear_manual: bool = False,
) -> SaleCalendarSettings:
    row = get_settings(db)
    if enabled is not None:
        row.enabled = bool(enabled)
    if teaser_days is not None:
        row.teaser_days = max(1, min(14, int(teaser_days)))
    if schedule_mode is not None:
        mode = str(schedule_mode).strip().lower()
        if mode in ("auto", "scheduled", "manual"):
            row.schedule_mode = mode
    if clear_scheduled:
        row.scheduled_sale_date = None
        row.scheduled_discount_percent = None
    elif scheduled_sale_date is not None:
        row.scheduled_sale_date = _parse_optional_date(scheduled_sale_date)
    if scheduled_discount_percent is not None:
        row.scheduled_discount_percent = Decimal(str(scheduled_discount_percent))
    if clear_manual:
        row.manual_sale_date = None
        row.manual_discount_percent = None
    elif manual_sale_date is not None:
        row.manual_sale_date = _parse_optional_date(manual_sale_date)
    if manual_discount_percent is not None:
        row.manual_discount_percent = Decimal(str(manual_discount_percent))
    db.commit()
    db.refresh(row)
    return row


def list_month_rules(db: Session) -> List[SaleCalendarMonthRule]:
    sale_calendar_svc.ensure_sale_calendar_defaults(db)
    return db.query(SaleCalendarMonthRule).order_by(SaleCalendarMonthRule.month.asc()).all()


def update_month_rule(
    db: Session,
    *,
    month: int,
    enabled: Optional[bool] = None,
    discount_percent_override: Optional[float] = None,
    clear_override: bool = False,
) -> SaleCalendarMonthRule:
    sale_calendar_svc.ensure_sale_calendar_defaults(db)
    row = db.query(SaleCalendarMonthRule).filter(SaleCalendarMonthRule.month == month).first()
    if not row:
        row = SaleCalendarMonthRule(month=month, enabled=True)
        db.add(row)
    if enabled is not None:
        row.enabled = bool(enabled)
    if clear_override:
        row.discount_percent_override = None
    elif discount_percent_override is not None:
        row.discount_percent_override = Decimal(str(discount_percent_override))
    db.commit()
    db.refresh(row)
    return row
