"""Đăng ký session import Excel đang chạy — hủy ngay (rollback + cancel query Postgres)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_sessions: Dict[str, Any] = {}


def register_import_session(job_id: str, db: Any) -> None:
    jid = (job_id or "").strip()
    if not jid or db is None:
        return
    with _lock:
        _sessions[jid] = db


def unregister_import_session(job_id: str) -> None:
    jid = (job_id or "").strip()
    if not jid:
        return
    with _lock:
        _sessions.pop(jid, None)


def _cancel_dbapi_in_flight(db: Any) -> None:
    """Hủy query đang chạy trên connection (psycopg2/psycopg3)."""
    try:
        conn = db.connection()
        raw = getattr(conn, "connection", None)
        if raw is not None and hasattr(raw, "cancel"):
            raw.cancel()
    except Exception as exc:
        logger.debug("import cancel dbapi.cancel: %s", exc)


def force_abort_import_session(job_id: str) -> bool:
    """
    Hủy ngay import đang chạy: rollback, cancel query in-flight, đóng session.
    Gọi từ thread HTTP cancel — session thuộc thread import worker.
    """
    with _lock:
        db = _sessions.pop(job_id, None)
    if db is None:
        return False
    try:
        db.rollback()
    except Exception as exc:
        logger.warning("force_abort import rollback job=%s: %s", job_id, exc)
    _cancel_dbapi_in_flight(db)
    try:
        db.close()
    except Exception as exc:
        logger.warning("force_abort import close job=%s: %s", job_id, exc)
    logger.info("force_abort import session job=%s", job_id)
    return True
