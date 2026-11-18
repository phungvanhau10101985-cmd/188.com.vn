"""CPU và RAM của cả máy. Khách đông thì mọi việc nền chờ.

Ngưỡng mặc định: chặn khi CPU hoặc RAM đã dùng ≥ 85%, cho chạy lại khi cả hai ≤ 80%.
CPU lấy từ /proc/stat (iowait tính là đang bận), mẫu 5 giây trong nền.
RAM lấy MemAvailable / MemTotal. Không đọc được thì cho chạy, khỏi kẹt dev Windows.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SAMPLE_SECONDS = 5.0

_state_lock = threading.Lock()
_cpu_pct: Optional[float] = None
_prev_idle_total: Optional[tuple[int, int]] = None
_blocked = False
_sampler_started = False
_last_log_mono = 0.0
_last_logged_blocked: Optional[bool] = None


def reset_for_tests() -> None:
    global _cpu_pct, _prev_idle_total, _blocked, _sampler_started
    global _last_log_mono, _last_logged_blocked
    with _state_lock:
        _cpu_pct = None
        _prev_idle_total = None
        _blocked = False
        _sampler_started = False
        _last_log_mono = 0.0
        _last_logged_blocked = None


def pressure_enabled() -> bool:
    raw = os.getenv("HOST_PRESSURE_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _thresholds() -> tuple[float, float]:
    try:
        block = float(os.getenv("HOST_PRESSURE_BLOCK_PCT", "85") or 85)
    except ValueError:
        block = 85.0
    try:
        resume = float(os.getenv("HOST_PRESSURE_RESUME_PCT", "80") or 80)
    except ValueError:
        resume = 80.0
    if resume > block:
        resume = block
    return block, resume


def cpu_idle_total(line: str) -> Optional[tuple[int, int]]:
    """idle chỉ là cột idle. iowait tính là máy đang bận (Postgres chờ đĩa)."""
    parts = (line or "").split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    try:
        nums = [int(part) for part in parts[1:]]
    except ValueError:
        return None
    if len(nums) < 4:
        return None
    return nums[3], sum(nums)


def cpu_used_pct(previous: tuple[int, int], current: tuple[int, int]) -> Optional[float]:
    idle_delta = current[0] - previous[0]
    total_delta = current[1] - previous[1]
    if total_delta <= 0:
        return None
    used = (1.0 - (idle_delta / total_delta)) * 100.0
    return max(0.0, min(100.0, used))


def ram_used_pct_from_meminfo(text: str) -> Optional[float]:
    total_kb: Optional[int] = None
    available_kb: Optional[int] = None
    for line in (text or "").splitlines():
        if line.startswith("MemTotal:"):
            total_kb = _meminfo_kb(line)
        elif line.startswith("MemAvailable:"):
            available_kb = _meminfo_kb(line)
    if total_kb is None or available_kb is None or total_kb <= 0:
        return None
    used = (1.0 - (available_kb / total_kb)) * 100.0
    return max(0.0, min(100.0, used))


def decide_blocked(
    was_blocked: bool,
    cpu_pct: Optional[float],
    ram_pct: Optional[float],
    *,
    block_at: float = 85.0,
    resume_at: float = 80.0,
) -> bool:
    """Đang mở thì chặn nếu CPU hoặc RAM ≥ block. Đang chặn thì mở khi mọi số đã có đều ≤ resume."""
    if was_blocked:
        if cpu_pct is None and ram_pct is None:
            return False
        if cpu_pct is not None and cpu_pct > resume_at:
            return True
        if ram_pct is not None and ram_pct > resume_at:
            return True
        return False
    if cpu_pct is not None and cpu_pct >= block_at:
        return True
    if ram_pct is not None and ram_pct >= block_at:
        return True
    return False


def host_blocks_background() -> bool:
    """True = khách đang chiếm máy, việc nền chưa bắt đầu phải chờ."""
    if not pressure_enabled():
        return False
    if not _linux_proc():
        return False
    _ensure_sampler()
    ram_pct = _read_ram_used_pct()
    with _state_lock:
        cpu_pct = _cpu_pct
        was_blocked = _blocked
    block_at, resume_at = _thresholds()
    blocked = decide_blocked(
        was_blocked,
        cpu_pct,
        ram_pct,
        block_at=block_at,
        resume_at=resume_at,
    )
    with _state_lock:
        _blocked = blocked
    _log_state(blocked, cpu_pct, ram_pct)
    return blocked


def wait_while_host_busy(
    should_stop: Optional[Callable[[], bool]] = None,
    poll_seconds: float = 2.0,
) -> bool:
    """Chờ đến khi máy rảnh. False nếu should_stop bảo dừng giữa chừng."""
    while host_blocks_background():
        if should_stop is not None and should_stop():
            return False
        time.sleep(max(0.2, poll_seconds))
    return True


def _linux_proc() -> bool:
    return os.path.isfile("/proc/stat") and os.path.isfile("/proc/meminfo")


def _meminfo_kb(line: str) -> Optional[int]:
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _read_ram_used_pct() -> Optional[float]:
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            return ram_used_pct_from_meminfo(handle.read())
    except OSError:
        return None


def _read_cpu_line() -> Optional[str]:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return None
    line = (line or "").strip()
    return line or None


def _sample_cpu() -> None:
    global _cpu_pct, _prev_idle_total
    parsed = None
    line = _read_cpu_line()
    if line:
        parsed = cpu_idle_total(line)
    if parsed is None:
        return
    if _prev_idle_total is not None:
        used = cpu_used_pct(_prev_idle_total, parsed)
        if used is not None:
            _cpu_pct = used
    _prev_idle_total = parsed


def _sampler_loop() -> None:
    while True:
        try:
            with _state_lock:
                _sample_cpu()
        except Exception:
            logger.exception("host pressure không đọc được CPU")
        time.sleep(_SAMPLE_SECONDS)


def _ensure_sampler() -> None:
    global _sampler_started
    with _state_lock:
        if _sampler_started:
            return
        _sampler_started = True
        threading.Thread(
            target=_sampler_loop,
            name="host-pressure",
            daemon=True,
        ).start()


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "chưa có mẫu"
    return f"{value:.0f}%"


def _log_state(blocked: bool, cpu_pct: Optional[float], ram_pct: Optional[float]) -> None:
    global _last_log_mono, _last_logged_blocked
    now = time.monotonic()
    changed = blocked != _last_logged_blocked
    if not changed and (not blocked or now - _last_log_mono < 60):
        return
    _last_logged_blocked = blocked
    _last_log_mono = now
    if blocked:
        logger.info(
            "Khách đang chiếm máy (CPU %s, RAM %s) — cào, kiểm tra nguồn, bản địa hóa và phối đồ chờ.",
            _fmt(cpu_pct),
            _fmt(ram_pct),
        )
        return
    logger.info(
        "Máy đã rảnh cho việc nền (CPU %s, RAM %s).",
        _fmt(cpu_pct),
        _fmt(ram_pct),
    )
