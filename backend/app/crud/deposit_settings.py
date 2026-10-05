from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.deposit_settings import DepositSettings
from app.schemas.deposit_settings import DepositPercentOut, DepositPercentUpdate
from app.utils.ttl_cache import cache as ttl_cache

DEFAULT_PARTIAL_PERCENT = 30
DEFAULT_MIN_AMOUNT = 100_000
MIN_AMOUNT_FLOOR = 100_000
MIN_AMOUNT_CEILING = 50_000_000
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
