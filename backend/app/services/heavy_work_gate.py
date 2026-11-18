"""Lượt chạy cho việc nặng trên cùng một máy — không hoãn sang buổi tối.

Khách đông (CPU hoặc RAM cả máy ≥ 85%) thì việc nền chưa bắt đầu phải chờ.
Dưới ngưỡng, hai nhóm mỗi nhóm một việc tại một thời điểm:

- Trình duyệt: cào sản phẩm (ưu tiên) và kiểm tra nguồn hàng.
  Đang cào thì nguồn hàng chờ; cào xong thì nguồn hàng chạy tiếp ngay.
- Ảnh: bản địa hóa và phối đồ. Có việc thì chạy; không chồng lên nhau.
  Xong một việc thì việc kia chạy tiếp, kể cả ban ngày.

Kiểm tra nguồn vẫn chạy song song với bản địa hóa hoặc phối đồ.
Tắt khẩn: HEAVY_WORK_GATE_ENABLED=0.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional, TypeVar

logger = logging.getLogger(__name__)

STALE_SECONDS = 40.0
_HEARTBEAT_SECONDS = 5.0

# role -> (group, priority). Số lớn hơn được lấy lượt trước trong cùng nhóm.
ROLES: dict[str, tuple[str, int]] = {
    "listing_crawl": ("browser", 100),
    "source_stock": ("browser", 10),
    "image_localization": ("image", 50),
    "outfit_visual": ("image", 50),
}

ROLE_LABEL = {
    "listing_crawl": "cào sản phẩm",
    "source_stock": "kiểm tra nguồn hàng",
    "image_localization": "bản địa hóa ảnh",
    "outfit_visual": "phối đồ",
}

GATE_DIR = Path(__file__).resolve().parents[2] / "runtime" / "heavy-work"

_state_lock = threading.Lock()
_counts: dict[str, int] = {}
_camped: set[str] = set()
_holding_tokens: set[str] = set()
_last_log: dict[str, float] = {}

T = TypeVar("T")


def gate_enabled() -> bool:
    raw = os.getenv("HEAVY_WORK_GATE_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def reset_for_tests() -> None:
    with _state_lock:
        _counts.clear()
        _camped.clear()
        _holding_tokens.clear()
        _last_log.clear()


class _DummyLease:
    """Cổng tắt hoặc lỗi đĩa — không chặn việc."""

    def release(self) -> None:
        return None


class _Lease:
    def __init__(self, role: str, group: str, token: str) -> None:
        self.role = role
        self.group = group
        self.token = token
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"heavy-work-{role}",
            daemon=True,
        )
        self._thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(_HEARTBEAT_SECONDS):
            if not _touch_hold(self):
                return

    def release(self) -> None:
        if self._stop.is_set():
            _release_hold(self)
            return
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)
        _release_hold(self)


def clear_camp(role: str) -> None:
    """Bỏ hàng chờ khi không còn việc (để nhóm kia không bị chặn suông)."""
    if role not in ROLES:
        return
    with _state_lock:
        camping = role in _camped
        if camping:
            _camped.discard(role)
    if camping:
        _leave(role)


@contextmanager
def heavy_work_slot(
    role: str,
    *,
    block: bool = True,
    poll_seconds: float = 2.0,
) -> Iterator[object]:
    """Giữ lượt đến khi thoát. block=True thì chờ, không bỏ việc."""
    if role not in ROLES:
        raise ValueError(role)
    if not gate_enabled():
        yield _DummyLease()
        return

    entered = False
    lease: Optional[_Lease] = None
    try:
        _enter(role)
        entered = True
        token = uuid.uuid4().hex
        while True:
            if _host_busy_for_background():
                if not block:
                    break
                time.sleep(max(0.2, poll_seconds))
                continue
            _publish_wait(role, token)
            lease = _try_claim(role, token)
            if lease is not None or not block:
                break
            _log_wait(role)
            time.sleep(max(0.2, poll_seconds))
    except Exception:
        logger.exception("heavy-work gate lỗi role=%s — cho chạy để khỏi kẹt hàng", role)
        _force_release_our_hold(role)
        lease = None
        if block:
            lease_out: object = _DummyLease()
        else:
            lease_out = None
        try:
            yield lease_out
        finally:
            if entered:
                _leave(role)
        return

    try:
        if lease is None:
            yield None
        else:
            yield lease
    finally:
        if lease is not None:
            try:
                lease.release()
            except Exception:
                logger.exception("heavy-work release role=%s", role)
        if entered:
            _leave(role)


def poll_heavy_work(role: str, *, camp: bool = False) -> Optional[object]:
    """Lấy lượt ngay. Không có thì trả None.

    camp=True: giữ chỗ trong hàng chờ để lần sau còn thứ tự (bản địa hóa).
    Process này đang giữ đúng role thì trả None, không xếp thêm chỗ.
    """
    if role not in ROLES:
        raise ValueError(role)
    if not gate_enabled():
        return _DummyLease()
    try:
        return _poll(role, camp=camp)
    except Exception:
        logger.exception("heavy-work gate lỗi role=%s — cho chạy để khỏi kẹt hàng", role)
        clear_camp(role)
        _force_release_our_hold(role)
        return _DummyLease()


def _host_busy_for_background() -> bool:
    try:
        from app.services.host_pressure import host_blocks_background

        return bool(host_blocks_background())
    except Exception:
        logger.exception("host pressure lỗi — cho việc nền chạy để khỏi kẹt")
        return False


def _poll(role: str, *, camp: bool) -> Optional[_Lease]:
    if _process_holds(role):
        return None
    if _host_busy_for_background():
        return None
    with _state_lock:
        already = role in _camped
        if not already:
            _camped.add(role)
    if not already:
        _enter(role)
    token = uuid.uuid4().hex
    _publish_wait(role, token)
    lease = _try_claim(role, token)
    if lease is None:
        if not camp:
            with _state_lock:
                _camped.discard(role)
            _leave(role)
        else:
            _log_wait(role)
        return None
    with _state_lock:
        _camped.discard(role)
    _leave(role)
    return lease


def _enter(role: str) -> None:
    with _state_lock:
        _counts[role] = _counts.get(role, 0) + 1


def _leave(role: str) -> None:
    with _state_lock:
        n = _counts.get(role, 0) - 1
        if n <= 0:
            _counts.pop(role, None)
            delete = True
        else:
            _counts[role] = n
            delete = False
    if delete:
        group = ROLES[role][0]
        _unlink(_wait_path(group, role))


def _process_holds(role: str) -> bool:
    group = ROLES[role][0]
    data = _read_json(_hold_path(group))
    if not data or _is_stale(data):
        return False
    return data.get("role") == role and int(data.get("pid") or 0) == os.getpid()


def _publish_wait(role: str, token: str) -> None:
    group, priority = ROLES[role]

    def body() -> None:
        if token in _holding_tokens:
            return
        path = _wait_path(group, role)
        now = time.time()
        since = now
        existing = _read_json(path)
        if existing and not _is_stale(existing):
            try:
                since = float(existing.get("want_since") or now)
            except (TypeError, ValueError):
                since = now
        _atomic_write(
            path,
            {
                "role": role,
                "group": group,
                "priority": priority,
                "want_since": since,
                "heartbeat": now,
                "pid": os.getpid(),
            },
        )

    _with_mutex(group, body)


def _try_claim(role: str, token: str) -> Optional[_Lease]:
    group, priority = ROLES[role]
    claimed = False

    def body() -> None:
        nonlocal claimed
        _reap_hold(group)
        waits = _fresh_waits(group)
        winner = _pick_winner(group, waits)
        if winner != role:
            return
        hold = _hold_path(group)
        existing = _read_json(hold)
        if existing and not _is_stale(existing):
            return
        if existing:
            _unlink(hold)
        now = time.time()
        _atomic_write(
            hold,
            {
                "role": role,
                "group": group,
                "priority": priority,
                "token": token,
                "pid": os.getpid(),
                "heartbeat": now,
            },
        )
        _holding_tokens.add(token)
        _unlink(_wait_path(group, role))
        claimed = True

    _with_mutex(group, body)
    if not claimed:
        return None
    return _Lease(role, group, token)


def _pick_winner(group: str, waits: list[dict]) -> Optional[str]:
    if not waits:
        return None
    best = max(int(item.get("priority") or 0) for item in waits)
    top = [item for item in waits if int(item.get("priority") or 0) == best]
    roles = {str(item.get("role") or "") for item in top}
    last = _read_turn(group)
    if len(roles) > 1 and last in roles:
        narrowed = [item for item in top if str(item.get("role") or "") != last]
        if narrowed:
            top = narrowed
    top.sort(key=lambda item: (float(item.get("want_since") or 0), str(item.get("role") or "")))
    return str(top[0].get("role") or "") or None


def _fresh_waits(group: str) -> list[dict]:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    found: list[dict] = []
    for path in GATE_DIR.glob(f"wait__{group}__*.json"):
        data = _read_json(path)
        if not data or _is_stale(data):
            _unlink(path)
            continue
        found.append(data)
    return found


def _reap_hold(group: str) -> None:
    path = _hold_path(group)
    data = _read_json(path)
    if data and _is_stale(data):
        _unlink(path)


def _touch_hold(lease: _Lease) -> bool:
    def body() -> bool:
        if lease._stop.is_set():
            return False
        path = _hold_path(lease.group)
        data = _read_json(path)
        if not data or data.get("token") != lease.token:
            return False
        data["heartbeat"] = time.time()
        data["pid"] = os.getpid()
        _atomic_write(path, data)
        return True

    try:
        return bool(_with_mutex(lease.group, body))
    except Exception:
        logger.exception("heavy-work heartbeat role=%s", lease.role)
        return True


def _release_hold(lease: _Lease) -> None:
    def body() -> None:
        _holding_tokens.discard(lease.token)
        path = _hold_path(lease.group)
        data = _read_json(path)
        if data and data.get("token") == lease.token:
            _unlink(path)
            _atomic_write(
                _turn_path(lease.group),
                {"role": lease.role, "at": time.time()},
            )

    try:
        _with_mutex(lease.group, body)
    except Exception:
        logger.exception("heavy-work release file role=%s", lease.role)


def _force_release_our_hold(role: str) -> None:
    group = ROLES[role][0]

    def body() -> None:
        path = _hold_path(group)
        data = _read_json(path)
        if not data:
            return
        if data.get("role") == role and int(data.get("pid") or 0) == os.getpid():
            token = str(data.get("token") or "")
            if token:
                _holding_tokens.discard(token)
            _unlink(path)

    try:
        _with_mutex(group, body)
    except Exception:
        logger.debug("heavy-work force release failed role=%s", role, exc_info=True)


def _read_turn(group: str) -> str:
    data = _read_json(_turn_path(group))
    if not data:
        return ""
    return str(data.get("role") or "")


def _log_wait(role: str) -> None:
    now = time.monotonic()
    if now - _last_log.get(role, 0.0) < 60:
        return
    _last_log[role] = now
    group = ROLES[role][0]
    holder = _read_json(_hold_path(group)) or {}
    holder_role = str(holder.get("role") or "")
    if holder_role == role:
        other = "lượt trước của chính nó"
    elif holder_role:
        other = ROLE_LABEL.get(holder_role, holder_role)
    else:
        other = "việc cùng nhóm"
    logger.info(
        "%s chờ %s xong rồi chạy tiếp (không hoãn sang buổi tối).",
        ROLE_LABEL.get(role, role),
        other,
    )


def _is_stale(data: dict) -> bool:
    try:
        heartbeat = float(data.get("heartbeat") or 0)
    except (TypeError, ValueError):
        return True
    if time.time() - heartbeat > STALE_SECONDS:
        return True
    try:
        pid = int(data.get("pid") or 0)
    except (TypeError, ValueError):
        return True
    if pid <= 0 or not _pid_alive(pid):
        return True
    return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    # Windows: os.kill(pid, 0) là CTRL_C_EVENT — không dùng để dò process.
    if os.name == "nt":
        import ctypes

        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _hold_path(group: str) -> Path:
    return GATE_DIR / f"hold__{group}.json"


def _wait_path(group: str, role: str) -> Path:
    return GATE_DIR / f"wait__{group}__{role}.json"


def _turn_path(group: str) -> Path:
    return GATE_DIR / f"turn__{group}.json"


def _mutex_path(group: str) -> Path:
    return GATE_DIR / f"mutex__{group}"


def _with_mutex(group: str, fn: Callable[[], T]) -> T:
    GATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _mutex_path(group)
    deadline = time.time() + 5
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > 5:
                _unlink(path)
                continue
            if time.time() > deadline:
                raise TimeoutError(f"heavy-work mutex {group}")
            time.sleep(0.02)
    try:
        return fn()
    finally:
        _unlink(path)


def _read_json(path: Path) -> Optional[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.debug("heavy-work unlink failed %s", path, exc_info=True)
