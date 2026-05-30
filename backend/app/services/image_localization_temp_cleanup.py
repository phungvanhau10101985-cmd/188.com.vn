"""Dọn file tạm pipeline bản địa hóa ảnh (temp_images, downloads/temp_download)."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set

from app.core.config import settings

logger = logging.getLogger(__name__)

_MERGE_FILE_PREFIXES = ("orig_", "merged_batch", "positions_batch")
_TEMP_SUBDIRS = ("current", "gemini_batches", "gemini_temp_keep", "split_images")


def _runtime_dir() -> Path:
    return Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR).resolve()


def _allowed_roots() -> tuple[Path, ...]:
    runtime = _runtime_dir()
    return (
        (runtime / "temp_images").resolve(),
        (runtime / "downloads" / "temp_download").resolve(),
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
    if removed:
        logger.info("Đã dọn %d file tạm image localization (sweep cuối job)", removed)
    return removed
