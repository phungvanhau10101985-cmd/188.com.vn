"""
Sale ngày trùng tháng: tháng lẻ 6%, tháng chẵn 8%, teaser T-3 → T-1, active đúng ngày (VN).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

_VN_TZ = timezone(timedelta(hours=7))

FEED_TITLE_PREFIX_TEASER = "Sắp giảm giá"
FEED_TITLE_PREFIX_ACTIVE = "Đang giảm giá"
SITE_SALE_TEST_DURATION_MINUTES = 10


@dataclass(frozen=True)
class SaleCalendarState:
    phase: Optional[str]  # None | "teaser" | "active"
    enabled: bool
    event_date: Optional[date]
    event_label: Optional[str]
    discount_percent: float
    teaser_days: int
    active_start_at: Optional[datetime]
    active_end_at: Optional[datetime]
    countdown_to: Optional[datetime]

    @property
    def is_teaser(self) -> bool:
        return self.phase == "teaser"

    @property
    def is_active(self) -> bool:
        return self.phase == "active"

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "phase": self.phase,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "event_label": self.event_label,
            "discount_percent": self.discount_percent,
            "teaser_days": self.teaser_days,
            "active_start_at": self.active_start_at.isoformat() if self.active_start_at else None,
            "active_end_at": self.active_end_at.isoformat() if self.active_end_at else None,
            "countdown_to": self.countdown_to.isoformat() if self.countdown_to else None,
            "feed_title_prefix_teaser": FEED_TITLE_PREFIX_TEASER,
            "feed_title_prefix_active": FEED_TITLE_PREFIX_ACTIVE,
        }


def _now_vn() -> datetime:
    return datetime.now(_VN_TZ)


def _default_discount_percent(month: int) -> float:
    return 6.0 if month % 2 == 1 else 8.0


def _sale_day(year: int, month: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(month, last))


def _event_label(sale_d: date) -> str:
    return f"Sale {sale_d.day}/{sale_d.month}"


def _active_bounds(sale_d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(sale_d, time(0, 0, 0), tzinfo=_VN_TZ)
    end = datetime.combine(sale_d, time(23, 59, 59), tzinfo=_VN_TZ)
    return start, end


def _load_settings(db: Session) -> tuple[bool, int]:
    from app.models.sale_calendar import SaleCalendarSettings

    try:
        row = db.query(SaleCalendarSettings).filter(SaleCalendarSettings.id == 1).first()
        if not row:
            return True, 3
        return bool(row.enabled), int(row.teaser_days or 3)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return True, 3


def _month_rule_map(db: Session) -> Dict[int, tuple[bool, Optional[float]]]:
    from app.models.sale_calendar import SaleCalendarMonthRule

    try:
        rows = db.query(SaleCalendarMonthRule).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return {}
    out: Dict[int, tuple[bool, Optional[float]]] = {}
    for r in rows:
        override = float(r.discount_percent_override) if r.discount_percent_override is not None else None
        out[int(r.month)] = (bool(r.enabled), override)
    return out


def _month_enabled(rules: Dict[int, tuple[bool, Optional[float]]], month: int) -> bool:
    if month in rules:
        return rules[month][0]
    return True


def _month_discount(rules: Dict[int, tuple[bool, Optional[float]]], month: int) -> float:
    if month in rules and rules[month][1] is not None:
        return max(0.0, min(100.0, float(rules[month][1])))
    return _default_discount_percent(month)


def _site_sale_test_row_for_user(db: Session, user) -> Optional[Any]:
    user_id = getattr(user, "id", None)
    user_email = (getattr(user, "email", None) or "").strip().lower()
    if not user_id and not user_email:
        return None
    try:
        from sqlalchemy import func, or_

        from app.models.admin import AdminUser
        from app.models.admin_feature_test import AdminFeatureTestSetting

        return (
            db.query(AdminFeatureTestSetting)
            .join(AdminUser, AdminUser.id == AdminFeatureTestSetting.admin_id)
            .filter(
                or_(
                    func.lower(AdminFeatureTestSetting.test_email) == user_email,
                    AdminUser.linked_user_id == user_id,
                )
            )
            .filter(AdminUser.is_active == True)  # noqa: E712
            .filter(AdminFeatureTestSetting.site_sale_test_enabled == True)  # noqa: E712
            .filter(AdminFeatureTestSetting.site_sale_test_expires_at.isnot(None))
            .filter(
                AdminFeatureTestSetting.site_sale_test_expires_at
                > datetime.now(timezone.utc).replace(tzinfo=None)
            )
            .first()
        )
    except Exception:
        return None


def is_site_sale_test_enabled(db: Session, user) -> bool:
    return _site_sale_test_row_for_user(db, user) is not None


def _build_site_sale_test_state(db: Session, phase: str, now: Optional[datetime] = None) -> SaleCalendarState:
    current = now or _now_vn()
    if current.tzinfo is None:
        current = current.replace(tzinfo=_VN_TZ)
    else:
        current = current.astimezone(_VN_TZ)

    today = current.date()
    _, teaser_days = _load_settings(db)
    teaser_days = max(1, min(14, int(teaser_days or 3)))
    rules = _month_rule_map(db)
    phase = (phase or "active").strip().lower()
    if phase not in ("teaser", "active"):
        phase = "active"

    if phase == "active":
        # Giả lập đúng ngày sale: giá giảm thật, countdown đến hết ngày.
        sale_d = today
        pct = _month_discount(rules, sale_d.month)
    else:
        # Giả lập đầu cửa sổ teaser (T-N): còn N ngày nữa mới tới ngày sale.
        sale_d = today + timedelta(days=teaser_days)
        pct = _month_discount(rules, sale_d.month)

    active_start, active_end = _active_bounds(sale_d)
    countdown = active_start if phase == "teaser" else active_end

    return SaleCalendarState(
        phase=phase,
        enabled=True,
        event_date=sale_d,
        event_label=f"[Test] {_event_label(sale_d)}",
        discount_percent=pct,
        teaser_days=teaser_days,
        active_start_at=active_start,
        active_end_at=active_end,
        countdown_to=countdown,
    )


def get_site_sale_test_state_for_user(
    db: Session,
    user,
    now: Optional[datetime] = None,
) -> Optional[SaleCalendarState]:
    row = _site_sale_test_row_for_user(db, user)
    if row is None:
        return None
    phase = (getattr(row, "site_sale_test_phase", None) or "active").strip().lower()
    return _build_site_sale_test_state(db, phase, now=now)


def resolve_sale_calendar_state(
    db: Session,
    now: Optional[datetime] = None,
    user=None,
) -> SaleCalendarState:
    """Trạng thái campaign hiện tại (teaser / active / không)."""
    if user is not None:
        test_state = get_site_sale_test_state_for_user(db, user, now=now)
        if test_state is not None:
            return test_state

    current = now or _now_vn()
    if current.tzinfo is None:
        current = current.replace(tzinfo=_VN_TZ)
    else:
        current = current.astimezone(_VN_TZ)

    today = current.date()
    global_enabled, teaser_days = _load_settings(db)
    rules = _month_rule_map(db)

    if not global_enabled:
        return SaleCalendarState(
            phase=None,
            enabled=False,
            event_date=None,
            event_label=None,
            discount_percent=0.0,
            teaser_days=teaser_days,
            active_start_at=None,
            active_end_at=None,
            countdown_to=None,
        )

    teaser_days = max(1, min(14, teaser_days))
    year = today.year

    candidates: List[tuple[date, str, float, datetime, datetime]] = []
    for y in (year - 1, year, year + 1):
        for month in range(1, 13):
            if not _month_enabled(rules, month):
                continue
            sale_d = _sale_day(y, month)
            teaser_start = sale_d - timedelta(days=teaser_days)
            if today < teaser_start or today > sale_d:
                continue
            pct = _month_discount(rules, month)
            active_start, active_end = _active_bounds(sale_d)
            phase = "active" if today == sale_d else "teaser"
            candidates.append((sale_d, phase, pct, active_start, active_end))

    if not candidates:
        return SaleCalendarState(
            phase=None,
            enabled=True,
            event_date=None,
            event_label=None,
            discount_percent=0.0,
            teaser_days=teaser_days,
            active_start_at=None,
            active_end_at=None,
            countdown_to=None,
        )

    # Ưu tiên active hôm nay, sau đó teaser gần nhất
    candidates.sort(key=lambda x: (0 if x[1] == "active" else 1, x[0]))
    sale_d, phase, pct, active_start, active_end = candidates[0]
    countdown = active_start if phase == "teaser" else active_end

    return SaleCalendarState(
        phase=phase,
        enabled=True,
        event_date=sale_d,
        event_label=_event_label(sale_d),
        discount_percent=pct,
        teaser_days=teaser_days,
        active_start_at=active_start,
        active_end_at=active_end,
        countdown_to=countdown,
    )


def apply_site_sale_to_price(list_price: float, state: SaleCalendarState) -> Dict[str, Any]:
    """Tính giá hiển thị theo phase sale site-wide."""
    base = max(0.0, float(list_price or 0))
    if base <= 0 or not state.enabled or not state.phase:
        return {
            "list_price": base,
            "display_price": base,
            "savings_amount": 0.0,
            "percent": 0.0,
            "phase": None,
        }

    pct = max(0.0, min(100.0, float(state.discount_percent)))
    savings = base * pct / 100.0
    sale_price = max(0.0, round(base - savings))

    if state.is_active:
        return {
            "list_price": base,
            "display_price": float(sale_price),
            "savings_amount": float(round(savings)),
            "percent": pct,
            "phase": "active",
        }

    if state.is_teaser:
        return {
            "list_price": base,
            "display_price": base,
            "savings_amount": float(round(savings)),
            "percent": pct,
            "phase": "teaser",
            "expected_sale_price": float(sale_price),
        }

    return {
        "list_price": base,
        "display_price": base,
        "savings_amount": 0.0,
        "percent": 0.0,
        "phase": None,
    }


def enrich_product_payload_with_site_sale(payload: Dict[str, Any], state: SaleCalendarState) -> None:
    """Gắn site_sale + original_price vào dict sản phẩm API."""
    base = float(payload.get("price") or 0)
    pricing = apply_site_sale_to_price(base, state)
    payload["site_sale"] = {
        **pricing,
        "event_label": state.event_label,
        "event_date": state.event_date.isoformat() if state.event_date else None,
        "countdown_to": state.countdown_to.isoformat() if state.countdown_to else None,
    }
    if state.is_active and pricing["savings_amount"] > 0:
        payload["original_price"] = base
        payload["price"] = pricing["display_price"]


def feed_title_with_sale_prefix(title: str, state: SaleCalendarState) -> str:
    raw = (title or "").strip()
    if not raw or not state.enabled or not state.phase:
        return raw
    prefix = FEED_TITLE_PREFIX_TEASER if state.is_teaser else FEED_TITLE_PREFIX_ACTIVE
    marker = f"{prefix} | "
    if raw.startswith(FEED_TITLE_PREFIX_TEASER) or raw.startswith(FEED_TITLE_PREFIX_ACTIVE):
        return raw
    return f"{marker}{raw}"


def feed_custom_label_for_teaser(state: SaleCalendarState) -> str:
    if state.is_teaser:
        return "sap_giam_gia"
    if state.is_active:
        return "dang_giam_gia"
    return ""


def feed_sale_price_tuple(
    list_price: float,
    state: SaleCalendarState,
    currency: str,
    *,
    format_price_fn,
    effective_gmc_fn,
) -> tuple[str, str]:
    """Trả (sale_price, sale_price_effective_date) cho feed — chỉ ngày active."""
    if not state.is_active or list_price <= 0:
        return "", ""
    pct = state.discount_percent
    sale_raw = list_price * (1.0 - pct / 100.0)
    cur = (currency or "VND").upper().strip()
    if cur == "VND":
        sale_raw = max(0.0, float(round(sale_raw)))
    else:
        sale_raw = max(0.0, sale_raw)
    sale_str = format_price_fn(sale_raw, currency)
    eff = effective_gmc_fn(state.active_start_at, state.active_end_at)
    return sale_str, eff


def gmc_effective_from_bounds(start: Optional[datetime], end: Optional[datetime]) -> str:
    """Chuỗi sale_price_effective_date cho GMC từ datetime VN."""
    if not start or not end:
        return ""

    def _fmt(dt: datetime) -> str:
        utc = dt.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    return f"{_fmt(start)}/{_fmt(end)}"


def list_upcoming_events(db: Session, *, limit: int = 6) -> List[Dict[str, Any]]:
    """Preview lịch sale cho admin."""
    today = _now_vn().date()
    global_enabled, teaser_days = _load_settings(db)
    rules = _month_rule_map(db)
    out: List[Dict[str, Any]] = []

    for y in (today.year, today.year + 1):
        for month in range(1, 13):
            if not _month_enabled(rules, month):
                continue
            sale_d = _sale_day(y, month)
            if sale_d < today:
                continue
            pct = _month_discount(rules, month)
            active_start, active_end = _active_bounds(sale_d)
            teaser_start = sale_d - timedelta(days=teaser_days)
            out.append(
                {
                    "event_date": sale_d.isoformat(),
                    "event_label": _event_label(sale_d),
                    "discount_percent": pct,
                    "teaser_start": teaser_start.isoformat(),
                    "active_start": active_start.isoformat(),
                    "active_end": active_end.isoformat(),
                    "month_parity": "le" if month % 2 == 1 else "chan",
                }
            )
    out.sort(key=lambda x: x["event_date"])
    return out[:limit]


def effective_unit_price(db: Session, list_price: float, user=None) -> float:
    """Giá bán hiệu lực cho checkout/cart khi site sale active."""
    state = resolve_sale_calendar_state(db, user=user)
    return float(apply_site_sale_to_price(list_price, state)["display_price"])


def ensure_sale_calendar_defaults(db: Session) -> None:
    from app.models.sale_calendar import SaleCalendarMonthRule, SaleCalendarSettings

    try:
        if not db.query(SaleCalendarSettings).filter(SaleCalendarSettings.id == 1).first():
            db.add(SaleCalendarSettings(id=1, enabled=True, teaser_days=3))
        for month in range(1, 13):
            if not db.query(SaleCalendarMonthRule).filter(SaleCalendarMonthRule.month == month).first():
                db.add(SaleCalendarMonthRule(month=month, enabled=True, discount_percent_override=None))
        db.commit()
    except Exception:
        db.rollback()
        raise
