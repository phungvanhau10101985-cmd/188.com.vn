"""
Tự phục hồi khi pool SQLAlchemy cạn — chạy nền trong process API (không cần cron 5 phút).

Khi probe DB qua pool thất bại (QueuePool timeout):
  1. Dọn idle-in-transaction (force)
  2. engine.dispose() — reset pool
  3. Nếu vẫn fail liên tiếp → thoát process để PM2 restart sạch
"""

from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Tuple

from sqlalchemy import text

from app.core.config import settings

_logger = logging.getLogger(__name__)

_daemon_started = False
_daemon_lock = threading.Lock()
_consecutive_probe_failures = 0
_startup_grace_until_mono = 0.0


def _pool_max_connections() -> int:
    return int(settings.DATABASE_POOL_SIZE) + int(settings.DATABASE_MAX_OVERFLOW)


def get_pool_usage_snapshot() -> dict:
    """Số connection đang checkout / giới hạn pool (không cần mở thêm connection)."""
    from app.db.session import engine

    pool = engine.pool
    try:
        checked_out = int(pool.checkedout())
    except Exception:
        checked_out = -1
    try:
        checked_in = int(pool.checkedin())
    except Exception:
        checked_in = -1
    try:
        overflow = int(pool.overflow())
    except Exception:
        overflow = -1
    pool_max = _pool_max_connections()
    return {
        "checked_out": checked_out,
        "checked_in": checked_in,
        "overflow": overflow,
        "pool_max": pool_max,
        "near_full": checked_out >= max(1, pool_max - 2) if checked_out >= 0 else False,
    }


def probe_db_pool(timeout_sec: float = 3.0) -> bool:
    """Probe SELECT 1 qua pool — dùng cho /health/storefront và monitor ngoài."""
    return _probe_db_via_pool(timeout_sec)


def _probe_db_via_pool(timeout_sec: float) -> bool:
    """Thử SELECT 1 qua pool — timeout ngắn, không chờ pool_timeout 20s."""

    def _try() -> bool:
        from app.db.session import engine

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="pool-probe") as ex:
        try:
            return bool(ex.submit(_try).result(timeout=max(1.0, timeout_sec)))
        except FuturesTimeoutError:
            return False
        except Exception as exc:
            _logger.debug("pool self-heal probe failed: %s", exc)
            return False


def _attempt_pool_recovery(*, reason: str) -> None:
    from app.db.pool_relief import release_stale_idle_in_transaction_connections
    from app.db.session import engine

    snap = get_pool_usage_snapshot()
    _logger.warning(
        "Pool self-heal recovery (%s): checked_out=%s pool_max=%s",
        reason,
        snap.get("checked_out"),
        snap.get("pool_max"),
    )

    terminated = release_stale_idle_in_transaction_connections(force=True)
    if terminated:
        _logger.warning("Pool self-heal: terminated %s idle-in-transaction session(s)", terminated)

    try:
        engine.dispose()
        _logger.warning("Pool self-heal: engine.dispose() — reset connection pool")
    except Exception as exc:
        _logger.warning("Pool self-heal: engine.dispose() failed: %s", exc)


def _maybe_exit_for_pm2_restart(*, reason: str) -> None:
    if not getattr(settings, "DATABASE_POOL_SELF_HEAL_EXIT_ON_FAILURE", True):
        return

    from app.services.ops_health_alert import collect_heavy_process_hints, notify_ops_health_alert

    notify_ops_health_alert(
        "pool_restart",
        "API sắp restart — pool DB không phục hồi",
        detail=reason,
        pool_snap=get_pool_usage_snapshot(),
        heavy_hints=collect_heavy_process_hints(),
        action="PM2 sẽ restart 188-api trong vài giây — nếu chưa ổn, chạy block lệnh SSH trong email.",
        force=True,
    )
    time.sleep(1.5)

    _logger.error(
        "Pool self-heal: %s — exiting process so PM2 restarts API (exit code 42)",
        reason,
    )
    os._exit(42)


def run_pool_self_heal_tick() -> Tuple[bool, Optional[str]]:
    """
    Một vòng kiểm tra. Trả (ok, message).
    Gọi từ daemon nền hoặc test.
    """
    global _consecutive_probe_failures

    if not getattr(settings, "IS_POSTGRESQL", False):
        return True, None
    if not getattr(settings, "DATABASE_POOL_SELF_HEAL_ENABLED", True):
        return True, None

    if time.monotonic() < _startup_grace_until_mono:
        return True, None

    probe_timeout = float(
        getattr(settings, "DATABASE_POOL_SELF_HEAL_PROBE_TIMEOUT_SECONDS", 3) or 3
    )
    snap = get_pool_usage_snapshot()
    near_full = snap.get("near_full")

    if near_full:
        from app.db.pool_relief import release_stale_idle_in_transaction_connections

        release_stale_idle_in_transaction_connections(force=True)

    if _probe_db_via_pool(probe_timeout):
        if _consecutive_probe_failures > 0:
            _logger.info(
                "Pool self-heal: DB probe OK again (was failing %s tick(s))",
                _consecutive_probe_failures,
            )
        _consecutive_probe_failures = 0
        return True, None

    _consecutive_probe_failures += 1
    fail_n = _consecutive_probe_failures
    max_fail = int(getattr(settings, "DATABASE_POOL_SELF_HEAL_MAX_FAILURES", 1) or 1)
    max_fail = max(1, max_fail)

    _logger.warning(
        "Pool self-heal: DB probe FAILED (%s/%s) pool=%s",
        fail_n,
        max_fail,
        snap,
    )

    from app.services.ops_health_alert import collect_heavy_process_hints, notify_ops_health_alert

    notify_ops_health_alert(
        "pool_exhaustion",
        "API pool DB kẹt — web có thể treo",
        detail=f"Probe DB thất bại lần {fail_n}/{max_fail}. Thường do QueuePool đầy (25/25).",
        pool_snap=snap,
        heavy_hints=collect_heavy_process_hints(),
        action="Hệ thống đang tự dispose pool; nếu web vẫn treo — chạy block lệnh SSH trong email.",
    )

    _attempt_pool_recovery(reason=f"probe_fail_{fail_n}")

    if _probe_db_via_pool(probe_timeout):
        _logger.info("Pool self-heal: recovered after dispose/relief")
        _consecutive_probe_failures = 0
        return True, None

    if fail_n >= max_fail:
        _maybe_exit_for_pm2_restart(
            reason=f"DB pool still unreachable after {fail_n} probe failure(s)"
        )

    return False, f"probe_fail_{fail_n}"


def _self_heal_loop() -> None:
    global _startup_grace_until_mono

    grace = max(15, int(getattr(settings, "DATABASE_POOL_SELF_HEAL_STARTUP_GRACE_SECONDS", 45) or 45))
    _startup_grace_until_mono = time.monotonic() + grace

    interval = max(
        10,
        int(getattr(settings, "DATABASE_POOL_SELF_HEAL_INTERVAL_SECONDS", 20) or 20),
    )
    _logger.info(
        "DB pool self-heal daemon started (interval=%ss grace=%ss probe=%ss max_fail=%s)",
        interval,
        grace,
        getattr(settings, "DATABASE_POOL_SELF_HEAL_PROBE_TIMEOUT_SECONDS", 3),
        getattr(settings, "DATABASE_POOL_SELF_HEAL_MAX_FAILURES", 2),
    )

    while True:
        try:
            run_pool_self_heal_tick()
        except Exception as exc:
            _logger.debug("pool self-heal loop: %s", exc)
        time.sleep(interval)


def start_pool_self_heal_daemon_if_enabled() -> None:
    global _daemon_started

    if not getattr(settings, "IS_POSTGRESQL", False):
        return
    if not getattr(settings, "DATABASE_POOL_SELF_HEAL_ENABLED", True):
        return

    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    t = threading.Thread(target=_self_heal_loop, name="db-pool-self-heal", daemon=True)
    t.start()
