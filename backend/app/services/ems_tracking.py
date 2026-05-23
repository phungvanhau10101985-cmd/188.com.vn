from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

_EMS_TRACKING_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{6,}VN$", re.IGNORECASE)
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 120


def ems_configured() -> bool:
    """Public MyEMS tracking không bắt buộc merchant token; vẫn giữ cờ nếu đã cấu hình token."""
    return True


def looks_like_ems_tracking_code(value: Optional[str]) -> bool:
    code = (value or "").strip().upper()
    if not code:
        return False
    if code.endswith("EMS"):
        code = code[:-3]
    return bool(_EMS_TRACKING_RE.match(code))


def should_fetch_ems_tracking(
    *,
    tracking_number: Optional[str],
    shipping_provider: Optional[str],
) -> bool:
    code = (tracking_number or "").strip()
    if not code:
        return False
    provider = (shipping_provider or "").strip().lower()
    if "ems" in provider:
        return True
    if not provider:
        return looks_like_ems_tracking_code(code)
    return looks_like_ems_tracking_code(code)


def _myems_item_code(tracking_code: str) -> str:
    code = tracking_code.strip().upper()
    if code.endswith("EMS"):
        return code
    return f"{code}EMS"


def _parse_traced_at(raw: Optional[str]) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    formats = (
        "%d/%m/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _event_datetime(row: dict[str, Any]) -> Optional[datetime]:
    traced = _parse_traced_at(row.get("NGAY_TRANG_THAI"))
    if traced:
        return traced
    ngay = (row.get("NGAY") or row.get("NGAY_PHAT") or "").strip()
    gio = (row.get("GIO") or row.get("GIO_TRANG_THAI") or "").strip()
    if ngay and gio:
        return _parse_traced_at(f"{ngay} {gio}")
    if ngay:
        return _parse_traced_at(ngay)
    return None


def _normalize_myems_events(raw_events: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, Any]] = []
    for row in raw_events:
        if not isinstance(row, dict):
            continue
        description = (row.get("TRANG_THAI") or row.get("description") or "").strip()
        if not description:
            continue
        events.append(
            {
                "status_code": None,
                "description": description,
                "address": (row.get("VI_TRI") or row.get("address") or "").strip() or None,
                "traced_at": _event_datetime(row),
            }
        )
    events.sort(key=lambda item: item.get("traced_at") or datetime.min, reverse=True)
    return events


def _normalize_legacy_events(raw_events: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, Any]] = []
    for row in raw_events:
        if not isinstance(row, dict):
            continue
        description = (row.get("description") or row.get("StatusName") or "").strip()
        if not description:
            continue
        status_raw = row.get("status")
        if status_raw is None:
            status_raw = row.get("StatusCode")
        try:
            status_code = int(status_raw) if status_raw is not None else None
        except (TypeError, ValueError):
            status_code = None
        events.append(
            {
                "status_code": status_code,
                "description": description,
                "address": (row.get("address") or row.get("Location") or "").strip() or None,
                "traced_at": _parse_traced_at(row.get("tracedate") or row.get("CreatedAt")),
            }
        )
    events.sort(key=lambda item: item.get("traced_at") or datetime.min, reverse=True)
    return events


def _cache_get(key: str) -> Optional[dict[str, Any]]:
    row = _CACHE.get(key)
    if not row:
        return None
    expires_at, payload = row
    if time.time() >= expires_at:
        _CACHE.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _CACHE[key] = (time.time() + _CACHE_TTL_SECONDS, payload)


def _fetch_myems_public_tracking(code: str) -> dict[str, Any]:
    base_url = (
        getattr(settings, "EMS_PUBLIC_API_BASE_URL", "")
        or getattr(settings, "EMS_API_BASE_URL", "")
        or "https://api.myems.vn"
    ).strip().rstrip("/")
    language = int(getattr(settings, "EMS_TRACKING_LANGUAGE", 0) or 0)
    timeout = int(getattr(settings, "EMS_API_TIMEOUT_SECONDS", 15) or 15)

    try:
        resp = requests.get(
            f"{base_url}/TrackAndTraceItemCode",
            params={"itemcode": _myems_item_code(code), "language": language},
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "188.com.vn/ems-tracking"},
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.RequestException as exc:
        logger.warning("MyEMS tracking request failed for %s: %s", code, exc)
        return {
            "available": True,
            "tracking_code": code,
            "events": [],
            "error": "Không thể kết nối EMS lúc này. Vui lòng thử lại sau.",
        }
    except ValueError:
        logger.warning("MyEMS tracking returned invalid JSON for %s", code)
        return {
            "available": True,
            "tracking_code": code,
            "events": [],
            "error": "Phản hồi EMS không hợp lệ.",
        }

    if not isinstance(body, dict) or body.get("Code") != "00":
        message = (body.get("Message") if isinstance(body, dict) else None) or ""
        return {
            "available": True,
            "tracking_code": code,
            "events": [],
            "error": message.strip() or "Không tìm thấy hành trình EMS cho mã vận đơn này.",
        }

    info = body.get("TBL_INFO") if isinstance(body.get("TBL_INFO"), dict) else {}
    events = _normalize_myems_events(body.get("List_TBL_DINH_VI"))
    if not events:
        events = _normalize_myems_events(body.get("List_TBL_DELIVERY"))

    current_status_description = (info.get("TRANG_THAI") or "").strip() or (
        events[0]["description"] if events else None
    )
    tracking_code = (info.get("MAE1") or code).strip() or code

    return {
        "available": True,
        "tracking_code": tracking_code,
        "reference_code": (info.get("MA_THAM_CHIEU") or "").strip() or None,
        "customer_code": (info.get("MA_KH") or "").strip() or None,
        "weight_grams": (info.get("KHOI_LUONG") or "").strip() or None,
        "receiver_address": (info.get("DIA_CHI_NHAN") or "").strip() or None,
        "current_status": None,
        "current_status_description": current_status_description,
        "events": events,
        "error": None,
    }


def _fetch_legacy_merchant_tracking(code: str) -> Optional[dict[str, Any]]:
    token = (getattr(settings, "EMS_MERCHANT_TOKEN", "") or "").strip()
    if not token:
        return None

    base_url = (getattr(settings, "EMS_LEGACY_API_BASE_URL", "") or "http://ws.ems.com.vn").strip().rstrip("/")
    timeout = int(getattr(settings, "EMS_API_TIMEOUT_SECONDS", 15) or 15)
    try:
        resp = requests.get(
            f"{base_url}/api/v1/orders/tracking/{code}",
            params={"merchant_token": token},
            timeout=timeout,
            headers={"Accept": "application/json", "User-Agent": "188.com.vn/ems-tracking"},
        )
        resp.raise_for_status()
        body = resp.json()
    except (requests.RequestException, ValueError):
        return None

    if not isinstance(body, dict) or body.get("code") != "success":
        return None

    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    events = _normalize_legacy_events(data.get("__get_status"))
    current_status = data.get("status")
    try:
        current_status = int(current_status) if current_status is not None else None
    except (TypeError, ValueError):
        current_status = None

    return {
        "available": True,
        "tracking_code": (data.get("tracking_code") or code),
        "current_status": current_status,
        "current_status_description": events[0]["description"] if events else None,
        "events": events,
        "error": None,
    }


def fetch_ems_tracking(tracking_code: str) -> dict[str, Any]:
    code = (tracking_code or "").strip().upper()
    if not code:
        return {"available": False, "error": "Thiếu mã vận đơn EMS."}

    cache_key = f"ems:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = _fetch_myems_public_tracking(code)
    if payload.get("error") and not payload.get("events"):
        legacy = _fetch_legacy_merchant_tracking(code)
        if legacy and legacy.get("events"):
            payload = legacy

    _cache_set(cache_key, payload)
    return payload


def build_ems_tracking_payload(
    *,
    tracking_number: Optional[str],
    shipping_provider: Optional[str],
) -> Optional[dict[str, Any]]:
    if not should_fetch_ems_tracking(
        tracking_number=tracking_number,
        shipping_provider=shipping_provider,
    ):
        return None
    return fetch_ems_tracking(tracking_number or "")
