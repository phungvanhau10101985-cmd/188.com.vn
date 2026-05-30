"""Đăng ký worker bản địa hóa ảnh đang chạy — phục vụ hủy ngay (terminate process / đóng Playwright)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from app.services.image_localization_job_runtime import terminate_job_worker

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_services: Dict[str, Any] = {}


def register_running_service(job_id: str, service: Any) -> None:
    jid = (job_id or "").strip()
    if not jid or service is None:
        return
    with _lock:
        _services[jid] = service


def unregister_running_service(job_id: str) -> None:
    jid = (job_id or "").strip()
    if not jid:
        return
    with _lock:
        _services.pop(jid, None)


def get_running_service(job_id: str) -> Optional[Any]:
    jid = (job_id or "").strip()
    if not jid:
        return None
    with _lock:
        return _services.get(jid)


def force_abort_running_service(job_id: str) -> bool:
    """Hủy ngay: kill subprocess trước, rồi đóng Playwright/session nếu còn trong process hiện tại."""
    terminated = terminate_job_worker(job_id)
    service = get_running_service(job_id)
    if service is None:
        return terminated
    try:
        if hasattr(service, "force_abort"):
            service.force_abort()
        elif hasattr(service, "close"):
            service.close()
        return True
    except Exception:
        logger.exception("force_abort_running_service failed job_id=%s", job_id)
        return terminated
