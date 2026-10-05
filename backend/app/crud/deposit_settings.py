from sqlalchemy.orm import Session

from app.models.deposit_settings import DepositSettings
from app.schemas.deposit_settings import DepositPercentOut, DepositPercentUpdate
from app.utils.ttl_cache import cache as ttl_cache

DEFAULT_PARTIAL_PERCENT = 30
_SINGLETON_ID = 1
_CACHE_KEY = "deposit_settings:partial_percent"
_CACHE_TTL_SECONDS = 60


def clamp_partial_percent(raw: object, default: int = DEFAULT_PARTIAL_PERCENT) -> int:
    try:
        n = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if n < 1 or n > 99:
        return default
    return n


def invalidate_public_cache() -> None:
    ttl_cache.invalidate(_CACHE_KEY)


def get_or_create_singleton(db: Session) -> DepositSettings:
    DepositSettings.__table__.create(bind=db.get_bind(), checkfirst=True)
    row = db.query(DepositSettings).filter(DepositSettings.id == _SINGLETON_ID).first()
    if row:
        row.partial_percent = clamp_partial_percent(row.partial_percent)
        return row
    row = DepositSettings(id=_SINGLETON_ID, partial_percent=DEFAULT_PARTIAL_PERCENT)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_partial_percent(db: Session) -> int:
    """Đọc mức cọc, không commit — an toàn khi gọi giữa transaction checkout."""

    def fetch() -> int:
        try:
            with db.begin_nested():
                row = db.query(DepositSettings).filter(DepositSettings.id == _SINGLETON_ID).first()
                raw = getattr(row, "partial_percent", None) if row is not None else None
            if raw is None:
                return DEFAULT_PARTIAL_PERCENT
            return clamp_partial_percent(raw)
        except Exception:
            return DEFAULT_PARTIAL_PERCENT

    return int(ttl_cache.get_or_fetch(_CACHE_KEY, _CACHE_TTL_SECONDS, fetch))


def to_out(row: DepositSettings) -> DepositPercentOut:
    return DepositPercentOut(partial_percent=clamp_partial_percent(row.partial_percent))


def update_partial_percent(db: Session, data: DepositPercentUpdate) -> DepositPercentOut:
    row = get_or_create_singleton(db)
    row.partial_percent = clamp_partial_percent(data.partial_percent)
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_public_cache()
    return to_out(row)
