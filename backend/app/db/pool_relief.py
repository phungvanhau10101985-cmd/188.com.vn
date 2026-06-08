"""
Giải phóng connection Postgres kẹt (idle in transaction) khi pool gần đầy.

- Mỗi connection mới: idle_in_transaction_session_timeout (statement_timeout chỉ khi bật).
- Daemon nền: khi số session idle-in-xact vượt ngưỡng, terminate các session kẹt quá lâu.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from sqlalchemy import text

from app.core.config import settings

_logger = logging.getLogger(__name__)

_daemon_started = False
_daemon_lock = threading.Lock()


def _pg_connect_options() -> str:
    """Gắn timeout Postgres lên mỗi connection từ pool SQLAlchemy."""
    parts = []
    idle_sec = max(5, int(getattr(settings, "DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS", 35) or 35))
    parts.append(f"-c idle_in_transaction_session_timeout={idle_sec}s")
    # statement_timeout toàn cục dễ cắt import/export admin — chỉ bật khi set > 0 (giây).
    stmt_sec = int(getattr(settings, "DATABASE_STATEMENT_TIMEOUT_SECONDS", 0) or 0)
    if stmt_sec > 0:
        parts.append(f"-c statement_timeout={max(10, stmt_sec)}s")
    return " ".join(parts)


def apply_postgres_connect_timeouts(connect_args: dict) -> dict:
    """Bổ sung options vào connect_args (PostgreSQL / psycopg2)."""
    if not getattr(settings, "IS_POSTGRESQL", False):
        return connect_args
    merged = dict(connect_args or {})
    opts = _pg_connect_options()
    existing = (merged.get("options") or "").strip()
    merged["options"] = f"{existing} {opts}".strip() if existing else opts
    return merged


def _database_name_from_url() -> Optional[str]:
    url = (settings.DATABASE_URL or "").strip()
    if not url or not getattr(settings, "IS_POSTGRESQL", False):
        return None
    try:
        from sqlalchemy.engine.url import make_url

        return make_url(url).database
    except Exception:
        return None


def apply_database_session_guardrails() -> None:
    """
    ALTER DATABASE — áp timeout idle-in-transaction cho mọi session (kể cả app khác cùng DB).
    Bỏ qua lỗi nếu user DB không đủ quyền.
    """
    if not getattr(settings, "IS_POSTGRESQL", False):
        return
    if not getattr(settings, "DATABASE_APPLY_PG_IDLE_TIMEOUT_ON_STARTUP", True):
        return

    db_name = _database_name_from_url()
    if not db_name:
        return

    idle_sec = max(5, int(getattr(settings, "DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_SECONDS", 35) or 35))
    stmt_sec = int(getattr(settings, "DATABASE_STATEMENT_TIMEOUT_SECONDS", 0) or 0)

    from app.db.session import engine

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(
                text(
                    f'ALTER DATABASE "{db_name.replace(chr(34), "")}" '
                    f"SET idle_in_transaction_session_timeout = '{idle_sec}s'"
                )
            )
            if stmt_sec > 0:
                conn.execute(
                    text(
                        f'ALTER DATABASE "{db_name.replace(chr(34), "")}" '
                        f"SET statement_timeout = '{max(10, stmt_sec)}s'"
                    )
                )
            else:
                conn.execute(
                    text(
                        f'ALTER DATABASE "{db_name.replace(chr(34), "")}" '
                        "RESET statement_timeout"
                    )
                )
        _logger.info(
            "Đã áp DB guardrails: idle_in_transaction=%ss statement=%s",
            idle_sec,
            f"{stmt_sec}s" if stmt_sec > 0 else "off",
        )
    except Exception as exc:
        _logger.warning("Không áp được ALTER DATABASE guardrails (bỏ qua): %s", exc)


def count_idle_in_transaction() -> int:
    from app.db.session import engine

    try:
        with engine.connect() as conn:
            return int(
                conn.execute(
                    text(
                        """
                        SELECT count(*)::int
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND state = 'idle in transaction'
                          AND pid <> pg_backend_pid()
                        """
                    )
                ).scalar()
                or 0
            )
    except Exception as exc:
        _logger.debug("count_idle_in_transaction failed: %s", exc)
        return 0


def release_stale_idle_in_transaction_connections(*, force: bool = False) -> int:
    """
    Terminate session idle-in-transaction quá lâu khi pool gần áp lực.
    Trả về số backend đã terminate.
    """
    if not getattr(settings, "IS_POSTGRESQL", False):
        return 0
    if not getattr(settings, "DATABASE_POOL_RELIEF_ENABLED", True):
        return 0

    min_idle = max(5, int(getattr(settings, "DATABASE_POOL_RELIEF_MIN_IDLE_SECONDS", 22) or 22))
    trigger_count = int(getattr(settings, "DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT", 14) or 14)
    aggressive_min = max(
        5,
        int(getattr(settings, "DATABASE_POOL_RELIEF_AGGRESSIVE_MIN_IDLE_SECONDS", 18) or 18),
    )
    aggressive_when = int(
        getattr(settings, "DATABASE_POOL_RELIEF_AGGRESSIVE_WHEN_IDLE_COUNT", 0) or 0
    )
    idle_count = count_idle_in_transaction()

    pool_max = int(settings.DATABASE_POOL_SIZE) + int(settings.DATABASE_MAX_OVERFLOW)
    if trigger_count <= 0:
        trigger_count = max(10, pool_max - 6)
    if aggressive_when <= 0:
        aggressive_when = max(trigger_count + 2, pool_max - 5)

    if not force and idle_count < trigger_count:
        return 0

    if idle_count >= aggressive_when:
        min_idle = min(min_idle, aggressive_min)

    from app.db.session import engine

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT pid
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'idle in transaction'
                      AND pid <> pg_backend_pid()
                      AND now() - state_change > make_interval(secs => :min_idle)
                    """
                ),
                {"min_idle": min_idle},
            ).fetchall()
            terminated = 0
            for (pid,) in rows:
                ok = conn.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": int(pid)},
                ).scalar()
                if ok:
                    terminated += 1
            if terminated:
                _logger.warning(
                    "Pool relief: terminated %s idle-in-transaction (idle_count=%s trigger=%s)",
                    terminated,
                    idle_count,
                    trigger_count,
                )
            return terminated
    except Exception as exc:
        _logger.warning("release_stale_idle_in_transaction_connections failed: %s", exc)
        return 0


def release_long_active_queries_when_pool_stressed(
    *,
    checked_out: int,
    pool_max: int,
    force: bool = False,
) -> int:
    """
    Pool gần đầy → terminate SELECT/query «active» chạy quá lâu (bot slug ILIKE, v.v.).
    Không dùng statement_timeout toàn cục để tránh cắt export admin 3–15 phút.
    """
    if not getattr(settings, "IS_POSTGRESQL", False):
        return 0
    min_age = int(getattr(settings, "DATABASE_ACTIVE_QUERY_KILL_SECONDS", 45) or 45)
    if min_age <= 0:
        return 0
    if pool_max <= 0:
        return 0
    if not force and checked_out < max(1, pool_max - 2):
        return 0

    from app.db.session import engine

    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT pid, left(query, 120) AS q
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                      AND state = 'active'
                      AND backend_type = 'client backend'
                      AND now() - query_start > make_interval(secs => :min_age)
                    """
                ),
                {"min_age": min_age},
            ).fetchall()
            terminated = 0
            for pid, qpreview in rows:
                ok = conn.execute(
                    text("SELECT pg_terminate_backend(:pid)"),
                    {"pid": int(pid)},
                ).scalar()
                if ok:
                    terminated += 1
                    _logger.warning(
                        "Pool relief: terminated long active query pid=%s age>=%ss q=%s",
                        pid,
                        min_age,
                        (qpreview or "")[:100],
                    )
            return terminated
    except Exception as exc:
        _logger.warning("release_long_active_queries_when_pool_stressed failed: %s", exc)
        return 0


def relieve_pool_pressure(*, force: bool = False) -> dict:
    """Idle-in-xact + query active quá lâu khi pool áp lực cao."""
    from app.db.pool_self_heal import get_pool_usage_snapshot

    snap = get_pool_usage_snapshot()
    checked_out = int(snap.get("checked_out") or 0)
    pool_max = int(snap.get("pool_max") or 0)
    idle_killed = release_stale_idle_in_transaction_connections(force=force)
    active_killed = release_long_active_queries_when_pool_stressed(
        checked_out=checked_out,
        pool_max=pool_max,
        force=force,
    )
    return {
        "idle_terminated": idle_killed,
        "active_terminated": active_killed,
        "pool": snap,
    }


def _pool_relief_loop() -> None:
    interval = max(10, int(getattr(settings, "DATABASE_POOL_RELIEF_INTERVAL_SECONDS", 15) or 15))
    while True:
        try:
            release_stale_idle_in_transaction_connections()
        except Exception as exc:
            _logger.debug("pool relief loop: %s", exc)
        time.sleep(interval)


def start_pool_relief_daemon_if_enabled() -> None:
    global _daemon_started
    if not getattr(settings, "IS_POSTGRESQL", False):
        return
    if not getattr(settings, "DATABASE_POOL_RELIEF_ENABLED", True):
        return

    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    apply_database_session_guardrails()
    t = threading.Thread(target=_pool_relief_loop, name="db-pool-relief", daemon=True)
    t.start()
    _logger.info(
        "DB pool relief daemon started (interval=%ss trigger>=%s min_idle=%ss aggressive>=%s@%ss)",
        settings.DATABASE_POOL_RELIEF_INTERVAL_SECONDS,
        settings.DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT,
        settings.DATABASE_POOL_RELIEF_MIN_IDLE_SECONDS,
        max(
            settings.DATABASE_POOL_RELIEF_TRIGGER_IDLE_COUNT + 2,
            settings.DATABASE_POOL_SIZE + settings.DATABASE_MAX_OVERFLOW - 5,
        )
        if settings.DATABASE_POOL_RELIEF_AGGRESSIVE_WHEN_IDLE_COUNT <= 0
        else settings.DATABASE_POOL_RELIEF_AGGRESSIVE_WHEN_IDLE_COUNT,
        settings.DATABASE_POOL_RELIEF_AGGRESSIVE_MIN_IDLE_SECONDS,
    )
