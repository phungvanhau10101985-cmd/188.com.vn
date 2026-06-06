"""
Retry helpers for transient PostgreSQL / SSL connection drops during long-running jobs.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")

_TRANSIENT_DB_MARKERS = (
    "ssl connection has been closed",
    "connection unexpectedly closed",
    "server closed the connection",
    "connection reset",
    "connection timed out",
    "could not connect to server",
    "connection already closed",
    "broken pipe",
    "terminating connection",
    "lost connection",
    "connection refused",
    "connection is closed",
)


def is_transient_db_error(exc: BaseException) -> bool:
    """True when failure is likely infra/connection related, not product data."""
    if isinstance(exc, DisconnectionError):
        return True
    if isinstance(exc, OperationalError):
        msg = str(exc).lower()
        return any(marker in msg for marker in _TRANSIENT_DB_MARKERS)
    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return is_transient_db_error(cause)
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_DB_MARKERS)


def _safe_rollback(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _safe_close(db: Session) -> None:
    try:
        db.close()
    except Exception:
        pass


def release_db_session(db: Session) -> None:
    """Return connection to pool after short DB work (before long CPU/IO)."""
    _safe_rollback(db)
    _safe_close(db)


def run_db_write(
    session_factory: Callable[[], Session],
    write_fn: Callable[[Session], T],
    *,
    max_attempts: int = 3,
) -> T:
    """Open a fresh session, run write_fn, commit — retry on transient connection errors."""
    last_exc: Optional[BaseException] = None
    for attempt in range(max_attempts):
        db = session_factory()
        try:
            result = write_fn(db)
            db.commit()
            return result
        except Exception as exc:
            last_exc = exc
            _safe_rollback(db)
            if not is_transient_db_error(exc) or attempt + 1 >= max_attempts:
                raise
            logger.warning(
                "Transient DB error (attempt %s/%s): %s",
                attempt + 1,
                max_attempts,
                exc,
            )
        finally:
            _safe_close(db)
    assert last_exc is not None
    raise last_exc
