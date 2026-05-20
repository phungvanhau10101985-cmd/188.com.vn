"""Khởi tạo cache nhóm danh mục hero nếu DB trống."""
from __future__ import annotations

import logging
import threading
import time

_log = logging.getLogger(__name__)


def _rebuild_once() -> None:
    from app.db.session import SessionLocal
    from app.crud.home_hero_category_cache import cache_has_groups, rebuild_home_hero_category_groups

    db = SessionLocal()
    try:
        if cache_has_groups(db):
            _log.info("home_hero_category_groups: đã có dữ liệu, bỏ qua rebuild startup")
            return
        _log.info("home_hero_category_groups: DB trống — bắt đầu rebuild…")
        rebuild_home_hero_category_groups(db)
        _log.info("home_hero_category_groups: rebuild startup xong")
    except Exception:
        _log.exception("home_hero_category_groups: rebuild startup thất bại")
    finally:
        db.close()


def start_home_hero_cache_daemon_if_needed(delay_seconds: float = 4.0) -> None:
    def _runner() -> None:
        time.sleep(delay_seconds)
        _rebuild_once()

    t = threading.Thread(target=_runner, name="home-hero-cache-rebuild", daemon=True)
    t.start()
