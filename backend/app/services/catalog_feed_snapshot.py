"""Feed Google / Meta / TikTok ghi ra file, rồi mới trả file.

Quét ~50k sản phẩm ngay trong StreamingResponse giữ transaction Postgres suốt
lúc mạng đối tác tải chậm (idle in transaction nhiều phút) và chiếm GIL của
process API. Ba feed cùng lúc là ba lần quét. File snapshot đóng connection
trước khi client tải, và chỉ một lần quét chạy tại một thời điểm.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CATALOG_FEED_MAX_AGE_SECONDS = 900

_BUILD_LOCK = threading.Lock()
_SCHEDULE_LOCK = threading.Lock()
_BUILDING: set[str] = set()


def catalog_feed_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / "temp_uploads" / "catalog_feeds"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _snapshot_path(name: str, directory: Path | None = None) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name)
    return (directory or catalog_feed_dir()) / f"{safe}.tsv"


def _is_fresh(path: Path, max_age_seconds: int) -> bool:
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    age = time.time() - path.stat().st_mtime
    return age < max_age_seconds


def _write_lines(path: Path, lines: Iterator[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            for index, line in enumerate(lines):
                handle.write(line)
                if not line.endswith("\n"):
                    handle.write("\n")
                if index and index % 100 == 0:
                    time.sleep(0)
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _build(name: str, produce: Callable[[Session], Iterator[str]], path: Path) -> None:
    from app.db.export_session import close_export_session, get_export_db_session

    db = get_export_db_session()
    try:
        _write_lines(path, produce(db))
    finally:
        close_export_session(db)
    logger.info("catalog feed snapshot written: %s (%s bytes)", name, path.stat().st_size)


def _schedule(name: str, produce: Callable[[Session], Iterator[str]], path: Path, max_age_seconds: int) -> None:
    with _SCHEDULE_LOCK:
        if name in _BUILDING:
            return
        _BUILDING.add(name)

    def _run() -> None:
        try:
            with _BUILD_LOCK:
                if _is_fresh(path, max_age_seconds):
                    return
                _build(name, produce, path)
        except Exception:
            logger.exception("catalog feed snapshot failed: %s", name)
        finally:
            with _SCHEDULE_LOCK:
                _BUILDING.discard(name)

    threading.Thread(target=_run, name=f"catalog-feed-{name}", daemon=True).start()


def ensure_catalog_feed_file(
    name: str,
    produce: Callable[[Session], Iterator[str]],
    *,
    max_age_seconds: int = CATALOG_FEED_MAX_AGE_SECONDS,
    directory: Path | None = None,
) -> Path:
    """Trả file TSV. Lần đầu chưa có file thì dựng ngay; lần sau trả file cũ và dựng nền."""
    path = _snapshot_path(name, directory)
    if _is_fresh(path, max_age_seconds):
        return path
    if path.is_file() and path.stat().st_size > 0:
        _schedule(name, produce, path, max_age_seconds)
        return path
    with _BUILD_LOCK:
        if _is_fresh(path, max_age_seconds):
            return path
        _build(name, produce, path)
    return path
