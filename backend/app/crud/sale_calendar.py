from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.sale_calendar import SaleCalendarMonthRule, SaleCalendarSettings
from app.services import sale_calendar as sale_calendar_svc


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


def update_settings(db: Session, *, enabled: Optional[bool] = None, teaser_days: Optional[int] = None) -> SaleCalendarSettings:
    row = get_settings(db)
    if enabled is not None:
        row.enabled = bool(enabled)
    if teaser_days is not None:
        row.teaser_days = max(1, min(14, int(teaser_days)))
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
