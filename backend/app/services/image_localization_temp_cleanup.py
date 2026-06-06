"""Dọn file tạm pipeline bản địa hóa ảnh (temp_images, downloads/temp_download)."""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

from app.core.config import settings

logger = logging.getLogger(__name__)

_MERGE_FILE_PREFIXES = ("orig_", "merged_batch", "positions_batch")
_TEMP_SUBDIRS = ("current", "gemini_batches", "gemini_temp_keep", "split_images")
_cleanup_daemon_lock = threading.Lock()
_cleanup_daemon_started = False


def _runtime_dir() -> Path:
    return Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR).resolve()


def _allowed_roots() -> tuple[Path, ...]:
    runtime = _runtime_dir()
    return (
        (runtime / "temp_images").resolve(),
        (runtime / "downloads" / "temp_download").resolve(),
        (runtime / "processed_images_cache").resolve(),
    )


def _is_allowed_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in _allowed_roots():
        if resolved == root or root in resolved.parents:
            return True
    return False


def _remove_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if not _is_allowed_path(path):
        logger.warning("Bỏ qua xóa file ngoài runtime temp: %s", path)
        return False
    try:
        path.unlink()
        return True
    except OSError as exc:
        logger.debug("Không xóa được %s: %s", path, exc)
        return False


def paths_from_merge_batches(batches_result: Optional[Dict[str, Any]]) -> Set[str]:
    """Thu thập đường dẫn file tạm tạo bởi ImageMerger cho một sản phẩm."""
    if not batches_result:
        return set()
    paths: Set[str] = set()
    for batch in batches_result.get("batches") or []:
        for key in ("merged_path", "positions_file"):
            value = batch.get(key)
            if isinstance(value, str) and value.strip():
                paths.add(value.strip())
    for info in (batches_result.get("column_mapping") or {}).values():
        if not isinstance(info, dict):
            continue
        original_path = info.get("original_path")
        if isinstance(original_path, str) and original_path.strip():
            paths.add(original_path.strip())
    return paths


def cleanup_merge_batch_files(batches_result: Optional[Dict[str, Any]]) -> int:
    """Xóa orig_/merged_/positions_ của một lượt xử lý sản phẩm."""
    removed = 0
    for raw in paths_from_merge_batches(batches_result):
        if _remove_file(Path(raw)):
            removed += 1
    if removed:
        logger.info("Đã dọn %d file tạm merge pipeline", removed)
    return removed


def cleanup_runtime_temp_now() -> int:
    """
    Dọn NGAY file tạm của lượt xử lý hiện tại.
    Dùng sau mỗi sản phẩm để tránh temp dồn làm đầy ổ.
    """
    runtime = _runtime_dir()
    temp_images = runtime / "temp_images"
    removed = 0
    removed += _cleanup_dir_entries(temp_images, max_age_hours=0, name_prefixes=_MERGE_FILE_PREFIXES)
    for subdir in _TEMP_SUBDIRS:
        removed += _cleanup_dir_entries(temp_images / subdir, max_age_hours=0)
    removed += _cleanup_dir_entries(runtime / "downloads" / "temp_download", max_age_hours=0)
    if removed:
        logger.info("Đã dọn %d file tạm image localization ngay sau lượt xử lý", removed)
    return removed


def _cleanup_dir_entries(
    directory: Path,
    *,
    max_age_hours: float,
    name_prefixes: Optional[tuple[str, ...]] = None,
) -> int:
    if not directory.is_dir():
        return 0
    if max_age_hours <= 0:
        cutoff = None
    else:
        cutoff = time.time() - max_age_hours * 3600
    removed = 0
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        logger.debug("Không đọc được thư mục %s: %s", directory, exc)
        return 0
    for entry in entries:
        if not entry.is_file():
            continue
        if name_prefixes and not entry.name.startswith(name_prefixes):
            continue
        if cutoff is not None:
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
        if _remove_file(entry):
            removed += 1
    return removed


def cleanup_stale_image_localization_temp(
    *,
    max_age_hours: Optional[float] = None,
) -> int:
    """
    Dọn file tạm còn sót (job crash, lần chạy cũ).
    Mặc định: IMAGE_LOCALIZATION_TEMP_CLEANUP_MAX_AGE_HOURS (1 giờ).
    """
    if max_age_hours is None:
        max_age_hours = float(
            getattr(settings, "IMAGE_LOCALIZATION_TEMP_CLEANUP_MAX_AGE_HOURS", 1) or 1
        )
    runtime = _runtime_dir()
    temp_images = runtime / "temp_images"
    removed = 0
    removed += _cleanup_dir_entries(
        temp_images,
        max_age_hours=max_age_hours,
        name_prefixes=_MERGE_FILE_PREFIXES,
    )
    for subdir in _TEMP_SUBDIRS:
        removed += _cleanup_dir_entries(
            temp_images / subdir,
            max_age_hours=max_age_hours,
        )
    removed += _cleanup_dir_entries(
        runtime / "downloads" / "temp_download",
        max_age_hours=max_age_hours,
    )
    # Cache mapping hash->CDN URL: không cần giữ quá lâu, tránh phình ổ đĩa theo thời gian.
    cache_age_hours = max(24.0, max_age_hours * 24.0)
    removed += _cleanup_dir_entries(
        runtime / "processed_images_cache",
        max_age_hours=cache_age_hours,
    )
    if removed:
        logger.info(
            "Đã dọn %d file tạm image localization cũ hơn %.1f giờ",
            removed,
            max_age_hours,
        )
    return removed


def cleanup_all_merge_temp_now() -> int:
    """Xóa ngay mọi orig_/merged_/positions_ và file trong temp subdirs (dùng khi job kết thúc)."""
    runtime = _runtime_dir()
    temp_images = runtime / "temp_images"
    removed = 0
    removed += _cleanup_dir_entries(temp_images, max_age_hours=0, name_prefixes=_MERGE_FILE_PREFIXES)
    for subdir in _TEMP_SUBDIRS:
        removed += _cleanup_dir_entries(temp_images / subdir, max_age_hours=0)
    removed += _cleanup_dir_entries(runtime / "downloads" / "temp_download", max_age_hours=0)
    removed += _cleanup_dir_entries(runtime / "processed_images_cache", max_age_hours=24.0 * 14)
    if removed:
        logger.info("Đã dọn %d file tạm image localization (sweep cuối job)", removed)
    return removed


def _periodic_cleanup_loop(interval_seconds: float) -> None:
    while True:
        try:
            cleanup_stale_image_localization_temp()
        except Exception:
            logger.exception("Periodic image-localization temp cleanup failed")
        time.sleep(max(30.0, float(interval_seconds)))


def start_periodic_image_localization_temp_cleanup_daemon_if_enabled() -> None:
    """
    Worker dọn temp định kỳ để quét file sót do crash/restart.
    Mặc định bật; khoảng cách mặc định 10 phút.
    """
    enabled = str(
        getattr(settings, "IMAGE_LOCALIZATION_TEMP_CLEANUP_SCHEDULER_ENABLED", True)
    ).strip().lower() in ("1", "true", "yes", "on")
    if not enabled:
        return
    interval_minutes = float(
        getattr(settings, "IMAGE_LOCALIZATION_TEMP_CLEANUP_INTERVAL_MINUTES", 10) or 10
    )
    interval_seconds = max(30.0, interval_minutes * 60.0)
    global _cleanup_daemon_started
    with _cleanup_daemon_lock:
        if _cleanup_daemon_started:
            return
        _cleanup_daemon_started = True
    threading.Thread(
        target=_periodic_cleanup_loop,
        args=(interval_seconds,),
        daemon=True,
        name="image-localization-temp-cleanup",
    ).start()


def runtime_free_disk_mb() -> float:
    """Dung lượng trống (MB) tại partition chứa runtime image localization."""
    runtime = _runtime_dir()
    try:
        usage = shutil.disk_usage(runtime)
    except Exception:
        usage = shutil.disk_usage(runtime.parent)
    return float(usage.free) / (1024.0 * 1024.0)


def guard_runtime_disk_space(
    *,
    warn_below_mb: Optional[int] = None,
    stop_below_mb: Optional[int] = None,
) -> float:
    """
    Van an toàn dung lượng đĩa cho pipeline bản địa hóa.
    - Nếu sắp đầy: log cảnh báo.
    - Nếu dưới ngưỡng stop: chạy cleanup khẩn rồi vẫn thấp thì raise RuntimeError để dừng job.
    """
    warn_mb = int(
        warn_below_mb
        if warn_below_mb is not None
        else getattr(settings, "IMAGE_LOCALIZATION_DISK_WARN_BELOW_MB", 4096) or 4096
    )
    stop_mb = int(
        stop_below_mb
        if stop_below_mb is not None
        else getattr(settings, "IMAGE_LOCALIZATION_DISK_STOP_BELOW_MB", 2048) or 2048
    )
    free_mb = runtime_free_disk_mb()
    if free_mb < warn_mb:
        logger.warning(
            "IMAGE_LOCALIZATION_DISK_LOW free=%.1fMB (warn<%sMB, stop<%sMB)",
            free_mb,
            warn_mb,
            stop_mb,
        )
    if free_mb >= stop_mb:
        return free_mb

    # Cleanup khẩn cấp khi dưới ngưỡng stop.
    removed = cleanup_all_merge_temp_now()
    free_after = runtime_free_disk_mb()
    logger.warning(
        "IMAGE_LOCALIZATION_DISK_EMERGENCY free_before=%.1fMB free_after=%.1fMB removed_files=%s",
        free_mb,
        free_after,
        removed,
    )
    if free_after < stop_mb:
        raise RuntimeError(
            f"Ổ đĩa gần đầy ({free_after:.1f}MB trống, cần >= {stop_mb}MB). "
            "Đã dừng job để tránh treo server."
        )
    return free_after
