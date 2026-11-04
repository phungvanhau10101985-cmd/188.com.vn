from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.deposit_settings import DepositSettings
from app.schemas.deposit_settings import DepositPercentOut, DepositPercentUpdate
from app.utils.ttl_cache import cache as ttl_cache

DEFAULT_PARTIAL_PERCENT = 30
DEFAULT_MIN_AMOUNT = 100_000
MIN_AMOUNT_FLOOR = 100_000
MIN_AMOUNT_CEILING = 50_000_000
# Giá trị hàng của đơn (sau giảm giá, không gồm ship) từ mốc này dùng HIGH_UNIT_MIN_PERCENT.
HIGH_ORDER_VALUE_VND = 3_000_000
HIGH_UNIT_PRICE_VND = HIGH_ORDER_VALUE_VND
HIGH_UNIT_MIN_PERCENT = 30
HIGH_ORDER_AMOUNT_FLOOR = 100_000
HIGH_ORDER_AMOUNT_CEILING = 500_000_000
_SINGLETON_ID = 1
_CACHE_KEY = "deposit_settings:rule:v3"
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


def clamp_high_order_amount(raw: object, default: int = HIGH_ORDER_VALUE_VND) -> int:
    """Mốc giá trị hàng (VND) để đổi sang % cọc đơn lớn. 0/NULL là cột mới, dùng 3.000.000đ."""
    if raw is None:
        return default
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if n <= 0:
        return default
    if n < HIGH_ORDER_AMOUNT_FLOOR:
        return HIGH_ORDER_AMOUNT_FLOOR
    if n > HIGH_ORDER_AMOUNT_CEILING:
        return HIGH_ORDER_AMOUNT_CEILING
    return n


def line_hits_high_unit_price(unit_price: object, threshold: object = HIGH_ORDER_VALUE_VND) -> bool:
    """Đơn giá >= mốc đơn lớn: một mình dòng đó đã đủ điều kiện."""
    return _as_decimal(unit_price) >= Decimal(clamp_high_order_amount(threshold))


def order_hits_high_value(goods: object, threshold: object = HIGH_ORDER_VALUE_VND) -> bool:
    """Giá trị hàng của đơn >= mốc thì dùng % cọc của đơn lớn."""
    return _as_decimal(goods) >= Decimal(clamp_high_order_amount(threshold))


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


def partial_percent_for_goods(
    configured: int,
    goods: object,
    threshold: object = HIGH_ORDER_VALUE_VND,
    high_percent: int = HIGH_UNIT_MIN_PERCENT,
) -> int:
    """% cọc một phần. Dưới mốc dùng % đơn nhỏ; từ mốc trở lên dùng % đơn lớn."""
    if order_hits_high_value(goods, threshold):
        return clamp_partial_percent(high_percent, default=HIGH_UNIT_MIN_PERCENT)
    return clamp_partial_percent(configured)


def partial_percent_for_lines(
    configured: int,
    rows: list,
    threshold: object = HIGH_ORDER_VALUE_VND,
    high_percent: int = HIGH_UNIT_MIN_PERCENT,
) -> int:
    """% cọc một phần theo tổng thành tiền các dòng (chưa trừ giảm giá đơn)."""
    return partial_percent_for_goods(
        configured,
        group_goods_value(rows),
        threshold,
        high_percent,
    )


def line_requires_deposit(
    product_flag: object,
    unit_price: object,
    threshold: object = HIGH_ORDER_VALUE_VND,
) -> bool:
    return bool(product_flag) or line_hits_high_unit_price(unit_price, threshold)


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
        raw_partial = getattr(row, "partial_percent", None)
        raw_min = getattr(row, "min_amount", None)
        raw_high = getattr(row, "high_order_amount", None)
        raw_high_pct = getattr(row, "high_order_percent", None)
        clamped_partial = clamp_partial_percent(raw_partial)
        clamped_min = clamp_min_amount(raw_min)
        clamped_high = clamp_high_order_amount(raw_high)
        clamped_high_pct = clamp_partial_percent(raw_high_pct, default=HIGH_UNIT_MIN_PERCENT)
        dirty = (
            raw_partial != clamped_partial
            or raw_min != clamped_min
            or raw_high != clamped_high
            or raw_high_pct != clamped_high_pct
        )
        row.partial_percent = clamped_partial
        row.min_amount = clamped_min
        row.high_order_amount = clamped_high
        row.high_order_percent = clamped_high_pct
        if dirty:
            db.add(row)
            db.commit()
            db.refresh(row)
        return row
    row = DepositSettings(
        id=_SINGLETON_ID,
        partial_percent=DEFAULT_PARTIAL_PERCENT,
        min_amount=DEFAULT_MIN_AMOUNT,
        high_order_amount=HIGH_ORDER_VALUE_VND,
        high_order_percent=HIGH_UNIT_MIN_PERCENT,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_rule(db: Session) -> tuple[int, int, int, int]:
    """Đọc (% đơn nhỏ, sàn VND, mốc đơn lớn, % đơn lớn). Không commit — an toàn giữa checkout."""

    def fetch() -> tuple[int, int, int, int]:
        try:
            with db.begin_nested():
                row = db.query(DepositSettings).filter(DepositSettings.id == _SINGLETON_ID).first()
                raw_pct = getattr(row, "partial_percent", None) if row is not None else None
                raw_min = getattr(row, "min_amount", None) if row is not None else None
                raw_high = getattr(row, "high_order_amount", None) if row is not None else None
                raw_high_pct = getattr(row, "high_order_percent", None) if row is not None else None
            if raw_pct is None and raw_min is None and raw_high is None and raw_high_pct is None:
                return (
                    DEFAULT_PARTIAL_PERCENT,
                    DEFAULT_MIN_AMOUNT,
                    HIGH_ORDER_VALUE_VND,
                    HIGH_UNIT_MIN_PERCENT,
                )
            return (
                clamp_partial_percent(raw_pct),
                clamp_min_amount(raw_min),
                clamp_high_order_amount(raw_high),
                clamp_partial_percent(raw_high_pct, default=HIGH_UNIT_MIN_PERCENT),
            )
        except Exception:
            return (
                DEFAULT_PARTIAL_PERCENT,
                DEFAULT_MIN_AMOUNT,
                HIGH_ORDER_VALUE_VND,
                HIGH_UNIT_MIN_PERCENT,
            )

    percent, minimum, high_order, high_percent = ttl_cache.get_or_fetch(
        _CACHE_KEY, _CACHE_TTL_SECONDS, fetch
    )
    return int(percent), int(minimum), int(high_order), int(high_percent)


def get_partial_percent(db: Session) -> int:
    return get_rule(db)[0]


def get_min_amount(db: Session) -> int:
    return get_rule(db)[1]


def to_out(row: DepositSettings) -> DepositPercentOut:
    return DepositPercentOut(
        partial_percent=clamp_partial_percent(row.partial_percent),
        min_amount=clamp_min_amount(getattr(row, "min_amount", None)),
        high_order_amount=clamp_high_order_amount(getattr(row, "high_order_amount", None)),
        high_order_percent=clamp_partial_percent(
            getattr(row, "high_order_percent", None),
            default=HIGH_UNIT_MIN_PERCENT,
        ),
    )


def update_partial_percent(db: Session, data: DepositPercentUpdate) -> DepositPercentOut:
    row = get_or_create_singleton(db)
    row.partial_percent = clamp_partial_percent(data.partial_percent)
    row.min_amount = clamp_min_amount(data.min_amount)
    if data.high_order_amount is not None:
        row.high_order_amount = clamp_high_order_amount(data.high_order_amount)
    if data.high_order_percent is not None:
        row.high_order_percent = clamp_partial_percent(
            data.high_order_percent,
            default=HIGH_UNIT_MIN_PERCENT,
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_public_cache()
    return to_out(row)
