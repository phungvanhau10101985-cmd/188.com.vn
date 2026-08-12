"""Warm + precompute định kỳ cây menu danh mục (prune offline)."""
from __future__ import annotations

import logging
import threading
import time

_log = logging.getLogger(__name__)

_daemon_started = False
_daemon_lock = threading.Lock()


def _warm_once(*, force: bool = False) -> None:
    from app.crud.category_menu_cache import warm_or_rebuild_menu_cache

    try:
        warm_or_rebuild_menu_cache(force=force)
    except Exception:
        _log.exception("category menu cache warm/rebuild failed")


def start_category_menu_cache_daemon_if_needed(delay_seconds: float = 3.0) -> None:
    """
    Startup: warm/rebuild sau vài giây.
    Periodic: force rebuild theo CATEGORY_MENU_PRECOMPUTE_INTERVAL_SECONDS (0 = tắt).
    """
    global _daemon_started

    with _daemon_lock:
        if _daemon_started:
            return
        _daemon_started = True

    def _runner() -> None:
        time.sleep(max(0.0, float(delay_seconds)))
        _warm_once(force=False)
        while True:
            try:
                from app.core.config import settings

                interval = float(getattr(settings, "CATEGORY_MENU_PRECOMPUTE_INTERVAL_SECONDS", 900) or 0)
            except Exception:
                interval = 900.0
            if interval <= 0:
                return
            time.sleep(interval)
            _log.info("category menu cache: periodic precompute (interval=%ss)", int(interval))
            _warm_once(force=True)

    t = threading.Thread(target=_runner, name="category-menu-cache-daemon", daemon=True)
    t.start()
