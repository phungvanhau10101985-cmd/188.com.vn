from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.deposit_settings import DepositSettings
from app.schemas.deposit_settings import DepositPercentOut, DepositPercentUpdate
from app.utils.ttl_cache import cache as ttl_cache

DEFAULT_PARTIAL_PERCENT = 30
DEFAULT_MIN_AMOUNT = 100_000
MIN_AMOUNT_FLOOR = 100_000
MIN_AMOUNT_CEILING = 50_000_000
# Giá trị hàng của đơn (sau giảm giá, không gồm ship) từ mốc này: cọc một phần không thấp hơn HIGH_UNIT_MIN_PERCENT.
HIGH_ORDER_VALUE_VND = 3_000_000
HIGH_UNIT_PRICE_VND = HIGH_ORDER_VALUE_VND
HIGH_UNIT_MIN_PERCENT = 30
_SINGLETON_ID = 1
_CACHE_KEY = "deposit_settings:rule"
_CACHE_TTL_SECONDS = 60


def clamp_partial_percent(raw: object, default: int = DEFAULT_PARTIAL_PERCENT) -> int:
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if n < 1 or n > 99:
        return default
    return n


def clamp_min_amount(raw: object, default: int = DEFAULT_MIN_AMOUNT) -> int:
    """Sàn cọc (VND). Dưới 100.000 thì nâng lên 100.000."""
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if n < MIN_AMOUNT_FLOOR:
        return MIN_AMOUNT_FLOOR
    if n > MIN_AMOUNT_CEILING:
        return MIN_AMOUNT_CEILING
    return n


def _as_decimal(raw: object) -> Decimal:
    try:
        return Decimal(str(0 if raw is None else raw))
    except Exception:
        return Decimal("0")


def line_hits_high_unit_price(unit_price: object) -> bool:
    """Đơn giá >= 3.000.000đ: một mình dòng đó đã đủ mốc cọc tối thiểu 30%."""
    return _as_decimal(unit_price) >= Decimal(HIGH_ORDER_VALUE_VND)


def order_hits_high_value(goods: object) -> bool:
    """Giá trị hàng của đơn >= 3.000.000đ thì cọc một phần không thấp hơn 30%."""
    return _as_decimal(goods) >= Decimal(HIGH_ORDER_VALUE_VND)


def line_goods_value(row: object) -> Decimal:
    """Tiền hàng của một dòng: thành tiền, hoặc đơn giá × số lượng."""
    if isinstance(row, dict):
        if row.get("total_price") is not None:
            return max(Decimal("0"), _as_decimal(row.get("total_price")))
        qty = _as_decimal(row.get("quantity") or 1)
        return max(Decimal("0"), _as_decimal(row.get("unit_price")) * qty)
    total = getattr(row, "total_price", None)
    if total is not None:
        return max(Decimal("0"), _as_decimal(total))
    unit = getattr(row, "unit_price", None)
    if unit is None:
        unit = getattr(row, "price", None)
    qty = _as_decimal(getattr(row, "quantity", None) or 1)
    return max(Decimal("0"), _as_decimal(unit) * qty)


def group_goods_value(rows: list) -> Decimal:
    return sum((line_goods_value(row) for row in rows), Decimal("0"))


def group_hits_high_order_value(rows: list) -> bool:
    return order_hits_high_value(group_goods_value(rows))


def group_has_high_unit_price(rows: list) -> bool:
    """Tên cũ. Mốc 3 triệu tính trên tổng tiền hàng của đơn, không trên đơn giá."""
    return group_hits_high_order_value(rows)


def partial_percent_for_goods(configured: int, goods: object) -> int:
    """% cọc một phần. Giá trị hàng >= 3.000.000đ thì không thấp hơn 30%."""
    pct = clamp_partial_percent(configured)
    if order_hits_high_value(goods):
        return max(pct, HIGH_UNIT_MIN_PERCENT)
    return pct


def partial_percent_for_lines(configured: int, rows: list) -> int:
    """% cọc một phần theo tổng thành tiền các dòng (chưa trừ giảm giá đơn)."""
    return partial_percent_for_goods(configured, group_goods_value(rows))


def line_requires_deposit(product_flag: object, unit_price: object) -> bool:
    return bool(product_flag) or line_hits_high_unit_price(unit_price)


def apply_partial_deposit(goods: Decimal, percent: int, min_amount: object = DEFAULT_MIN_AMOUNT) -> Decimal:
    """Cọc một phần = % giá trị hàng, nhưng không thấp hơn sàn và không vượt giá trị hàng."""
    base = max(Decimal("0"), Decimal(goods)).quantize(Decimal("0.01"))
    if base <= 0:
        return Decimal("0.00")
    pct = clamp_partial_percent(percent)
    raw = (base * Decimal(pct) / Decimal(100)).quantize(Decimal("0.01"))
    floor = Decimal(clamp_min_amount(min_amount)).quantize(Decimal("0.01"))
    amount = raw if raw >= floor else floor
    if amount > base:
        amount = base
    return amount.quantize(Decimal("0.01"))


def invalidate_public_cache() -> None:
    ttl_cache.invalidate(_CACHE_KEY)


def get_or_create_singleton(db: Session) -> DepositSettings:
    DepositSettings.__table__.create(bind=db.get_bind(), checkfirst=True)
    row = db.query(DepositSettings).filter(DepositSettings.id == _SINGLETON_ID).first()
    if row:
        row.partial_percent = clamp_partial_percent(row.partial_percent)
        clamped_min = clamp_min_amount(getattr(row, "min_amount", None))
        if int(getattr(row, "min_amount", 0) or 0) != clamped_min:
            row.min_amount = clamped_min
            db.add(row)
            db.commit()
            db.refresh(row)
        else:
            row.min_amount = clamped_min
        return row
    row = DepositSettings(
        id=_SINGLETON_ID,
        partial_percent=DEFAULT_PARTIAL_PERCENT,
        min_amount=DEFAULT_MIN_AMOUNT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_rule(db: Session) -> tuple[int, int]:
    """Đọc (%, sàn VND), không commit — an toàn khi gọi giữa transaction checkout."""

    def fetch() -> tuple[int, int]:
        try:
            with db.begin_nested():
                row = db.query(DepositSettings).filter(DepositSettings.id == _SINGLETON_ID).first()
                raw_pct = getattr(row, "partial_percent", None) if row is not None else None
                raw_min = getattr(row, "min_amount", None) if row is not None else None
            if raw_pct is None and raw_min is None:
                return DEFAULT_PARTIAL_PERCENT, DEFAULT_MIN_AMOUNT
            return clamp_partial_percent(raw_pct), clamp_min_amount(raw_min)
        except Exception:
            return DEFAULT_PARTIAL_PERCENT, DEFAULT_MIN_AMOUNT

    percent, minimum = ttl_cache.get_or_fetch(_CACHE_KEY, _CACHE_TTL_SECONDS, fetch)
    return int(percent), int(minimum)


def get_partial_percent(db: Session) -> int:
    return get_rule(db)[0]


def get_min_amount(db: Session) -> int:
    return get_rule(db)[1]


def to_out(row: DepositSettings) -> DepositPercentOut:
    return DepositPercentOut(
        partial_percent=clamp_partial_percent(row.partial_percent),
        min_amount=clamp_min_amount(getattr(row, "min_amount", None)),
    )


def update_partial_percent(db: Session, data: DepositPercentUpdate) -> DepositPercentOut:
    row = get_or_create_singleton(db)
    row.partial_percent = clamp_partial_percent(data.partial_percent)
    row.min_amount = clamp_min_amount(data.min_amount)
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_public_cache()
    return to_out(row)
