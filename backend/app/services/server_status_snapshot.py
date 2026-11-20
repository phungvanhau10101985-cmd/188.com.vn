"""Ảnh trạng thái máy cho trang quản trị. Chỉ tính khi có request, không lưu lịch sử."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.host_pressure import cpu_idle_total, cpu_used_pct, ram_used_pct_from_meminfo

_CPU_PREV: Optional[tuple[int, int]] = None
_PRESSURE_BLOCK_PCT = 85.0


def reset_cpu_sample_for_tests() -> None:
    global _CPU_PREV
    _CPU_PREV = None


def read_host_snapshot() -> Dict[str, Optional[float]]:
    """RAM tức thời. CPU là chênh giữa hai lần mở trang, không có luồng nền."""
    global _CPU_PREV
    text = _read_text("/proc/meminfo")
    stat = _read_text("/proc/stat")
    ram_pct = ram_used_pct_from_meminfo(text) if text else None
    total_mb, avail_mb = _meminfo_mb(text or "")
    cpu_pct = None
    current = cpu_idle_total(stat.splitlines()[0] if stat else "")
    if current is not None and _CPU_PREV is not None:
        cpu_pct = cpu_used_pct(_CPU_PREV, current)
    if current is not None:
        _CPU_PREV = current
    return {
        "mem_total_mb": total_mb,
        "mem_available_mb": avail_mb,
        "ram_used_pct": ram_pct,
        "cpu_used_pct": cpu_pct,
    }


def localization_rss_mb() -> Optional[int]:
    """RAM thật của worker bản địa hóa và process ảnh con. None nếu không có /proc."""
    if not os.path.isdir("/proc"):
        return None
    worker_pids = set()
    for pid in _proc_pids():
        cmd = _cmdline(pid)
        if "image_localization_worker.py" in cmd:
            worker_pids.add(pid)
    if not worker_pids:
        return 0
    total_kb = 0
    seen = set()
    for pid in list(worker_pids):
        total_kb += _rss_kb(pid)
        seen.add(pid)
    for pid in _proc_pids():
        if pid in seen:
            continue
        ppid = _ppid(pid)
        if ppid not in worker_pids:
            continue
        cmd = _cmdline(pid)
        if "spawn_main" in cmd or "imgloc-" in cmd or "image_localization" in cmd:
            total_kb += _rss_kb(pid)
    return int(total_kb // 1024)


def build_warnings(
    *,
    mem_available_mb: Optional[float],
    min_available_mb: int,
    cpu_used_pct: Optional[float],
    ram_used_pct: Optional[float],
    block_pct: float,
    localization_waiting: bool,
    localization_error: Optional[str],
    error_lines: List[str],
) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    if mem_available_mb is None:
        warnings.append({"level": "warning", "text": "Không đọc được RAM của máy."})
    elif mem_available_mb < min_available_mb:
        warnings.append(
            {
                "level": "warning",
                "text": f"RAM trống {int(mem_available_mb)}MB, dưới ngưỡng {min_available_mb}MB.",
            }
        )
    if cpu_used_pct is not None and cpu_used_pct >= block_pct:
        warnings.append({"level": "warning", "text": f"CPU máy {cpu_used_pct:.0f}%, từ {block_pct:.0f}%."})
    if ram_used_pct is not None and ram_used_pct >= block_pct:
        warnings.append(
            {"level": "warning", "text": f"RAM máy đã dùng {ram_used_pct:.0f}%, từ {block_pct:.0f}%."}
        )
    if localization_waiting:
        warnings.append({"level": "warning", "text": "Bản địa hóa đang chờ RAM trống."})
    if localization_error:
        warnings.append({"level": "error", "text": f"Job bản địa hóa lỗi: {localization_error}"})
    for line in error_lines:
        warnings.append({"level": "error", "text": line})
    return warnings


def build_server_status(db: Session) -> Dict[str, Any]:
    host = read_host_snapshot()
    min_mb = int(getattr(settings, "IMAGE_LOCALIZATION_RESUME_MIN_AVAILABLE_MB", 2000) or 2000)
    rss_mb = localization_rss_mb()
    jobs = _heavy_jobs(db, rss_mb)
    logs = _recent_error_lines(db)
    loc = next((item for item in jobs if item["key"] == "localization"), None)
    waiting = bool(loc and loc.get("waiting_ram"))
    loc_error = loc.get("error") if loc else None
    error_count = sum(1 for row in logs if row.get("status_code") and int(row["status_code"]) >= 500)
    warnings = build_warnings(
        mem_available_mb=host["mem_available_mb"],
        min_available_mb=min_mb,
        cpu_used_pct=host["cpu_used_pct"],
        ram_used_pct=host["ram_used_pct"],
        block_pct=_PRESSURE_BLOCK_PCT,
        localization_waiting=waiting,
        localization_error=loc_error,
        error_lines=[f"Có {error_count} lỗi HTTP 5xx trong 6 giờ qua."] if error_count else [],
    )
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            **host,
            "min_available_mb": min_mb,
            "pressure_block_pct": _PRESSURE_BLOCK_PCT,
            "localization_rss_mb": rss_mb,
        },
        "warnings": warnings,
        "jobs": jobs,
        "logs": logs,
    }


def _heavy_jobs(db: Session, rss_mb: Optional[int]) -> List[Dict[str, Any]]:
    return [
        _localization_job(db, rss_mb),
        _stock_job(db),
        _import_job(db),
    ]


def _localization_job(db: Session, rss_mb: Optional[int]) -> Dict[str, Any]:
    from sqlalchemy.orm import load_only

    from app.models.image_localization_job import ImageLocalizationJob

    light = load_only(
        ImageLocalizationJob.status,
        ImageLocalizationJob.phase,
        ImageLocalizationJob.message,
        ImageLocalizationJob.current,
        ImageLocalizationJob.total,
        ImageLocalizationJob.updated_at,
    )
    now = datetime.now(timezone.utc)
    active = (
        db.query(ImageLocalizationJob)
        .options(light)
        .filter(ImageLocalizationJob.status.in_(("queued", "running")))
        .order_by(ImageLocalizationJob.updated_at.desc())
        .first()
    )
    recent_error = (
        db.query(ImageLocalizationJob)
        .options(light)
        .filter(
            ImageLocalizationJob.status == "error",
            ImageLocalizationJob.updated_at >= now - timedelta(hours=6),
        )
        .order_by(ImageLocalizationJob.updated_at.desc())
        .first()
    )
    if active is None:
        detail = "Không chạy."
        if recent_error is not None:
            detail = f"Không chạy. Lỗi gần đây: {_clip(recent_error.message, 160)}"
        return {
            "key": "localization",
            "name": "Bản địa hóa ảnh",
            "running": False,
            "detail": detail,
            "rss_mb": rss_mb,
            "waiting_ram": False,
            "error": _clip(recent_error.message, 180) if recent_error is not None else None,
        }
    message = _clip(active.message, 180)
    waiting = (active.phase or "") == "waiting_ram" or "chờ RAM" in (active.message or "")
    current = int(active.current or 0)
    total = int(active.total or 0)
    progress = f"{current}/{total}" if total else str(current)
    rss_bit = f" RAM thật {rss_mb}MB." if rss_mb else ""
    return {
        "key": "localization",
        "name": "Bản địa hóa ảnh",
        "running": True,
        "detail": f"Đang chạy {progress}. {message}{rss_bit}",
        "rss_mb": rss_mb,
        "waiting_ram": waiting,
        "error": None,
    }


def _stock_job(db: Session) -> Dict[str, Any]:
    from app.models.source_stock_worker_state import SourceStockWorkerState
    from app.services.source_stock_checker import source_stock_worker_heartbeat_age_seconds

    row = db.query(SourceStockWorkerState).filter(SourceStockWorkerState.id == 1).first()
    age = source_stock_worker_heartbeat_age_seconds()
    fresh = age is not None and age <= 180
    checking = False
    detail = "Không chạy."
    if row is not None and row.paused:
        detail = "Đang tạm dừng."
    elif row is not None and row.checking_product_db_id and _recent(row.checking_started_at, minutes=20):
        checking = True
        detail = f"Đang kiểm tra sản phẩm #{row.checking_product_db_id}."
    elif fresh:
        detail = "Worker sống, không có sản phẩm đang kiểm tra."
    return {"key": "stock", "name": "Kiểm tra nguồn hàng", "running": checking, "detail": detail}


def _import_job(db: Session) -> Dict[str, Any]:
    from app.models.listing_import_queue_snapshot import ListingImportQueueSnapshot

    status_text = ListingImportQueueSnapshot.payload_json["run_status"].as_string()
    rows = (
        db.query(status_text)
        .order_by(ListingImportQueueSnapshot.updated_at.desc())
        .limit(5)
        .all()
    )
    for (status,) in rows:
        state = str(status or "")
        if state not in {"running", "pausing"}:
            continue
        label = "đang chạy" if state == "running" else "đang tạm dừng"
        return {
            "key": "import",
            "name": "Nhập danh mục",
            "running": True,
            "detail": f"Đợt nhập {label}.",
        }
    return {"key": "import", "name": "Nhập danh mục", "running": False, "detail": "Không chạy."}


def _recent_error_lines(db: Session) -> List[Dict[str, Any]]:
    from app.models.site_error_log import SiteErrorLog

    since = datetime.now(timezone.utc) - timedelta(hours=6)
    rows = (
        db.query(SiteErrorLog)
        .filter(SiteErrorLog.resolved.is_(False), SiteErrorLog.last_seen_at >= since)
        .order_by(SiteErrorLog.last_seen_at.desc())
        .limit(5)
        .all()
    )
    out = []
    for row in rows:
        code = f" HTTP {row.status_code}" if row.status_code else ""
        out.append(
            {
                "at": row.last_seen_at.isoformat() if row.last_seen_at else None,
                "text": _clip(f"{row.source}{code}: {row.message}", 200),
                "status_code": row.status_code,
            }
        )
    return out


def _meminfo_mb(text: str) -> tuple[Optional[int], Optional[int]]:
    total = avail = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            mb = int(parts[1]) // 1024
        except ValueError:
            continue
        if line.startswith("MemTotal:"):
            total = mb
        elif line.startswith("MemAvailable:"):
            avail = mb
    return total, avail


def _read_text(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _proc_pids() -> List[int]:
    out = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return out
    for name in names:
        if name.isdigit():
            out.append(int(name))
    return out


def _cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return handle.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def _rss_kb(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _ppid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def _recent(value: Optional[datetime], *, minutes: int) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - value <= timedelta(minutes=minutes)


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
