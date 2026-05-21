"""Chạy Playwright Sync API cho import 1688 trong worker thread riêng (Windows/uvicorn)."""
from __future__ import annotations

import threading
import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

# Luôn dồn Playwright vào 1 worker thread — tránh NotImplementedError trên Windows
# khi chạy từ FastAPI BackgroundTasks / anyio threadpool.
_IMPORT_PW_EXECUTOR: Optional[ThreadPoolExecutor] = None
_IMPORT_PW_LOCK = threading.Lock()


def _ensure_windows_playwright_event_loop_policy() -> None:
    if sys.platform != "win32":
        return
    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return
    if not isinstance(asyncio.get_event_loop_policy(), policy_cls):
        # Uvicorn on Windows may install Selector policy; Playwright needs
        # Proactor support to spawn the browser subprocess.
        asyncio.set_event_loop_policy(policy_cls())


def run_import_playwright_sync(fn: Callable[[], T], *, timeout_sec: float = 240.0) -> T:
    _ensure_windows_playwright_event_loop_policy()
    global _IMPORT_PW_EXECUTOR
    with _IMPORT_PW_LOCK:
        if _IMPORT_PW_EXECUTOR is None:
            _IMPORT_PW_EXECUTOR = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="import1688_pw",
            )
    return _IMPORT_PW_EXECUTOR.submit(lambda: (_ensure_windows_playwright_event_loop_policy(), fn())[1]).result(
        timeout=timeout_sec,
    )
