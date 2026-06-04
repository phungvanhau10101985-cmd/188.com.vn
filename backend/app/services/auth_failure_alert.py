"""
Cảnh báo email khi khách không đăng nhập được (OTP, Google, SMTP, …).
Người nhận: mọi email admin_users đang active (super_admin, admin, NV chốt đơn, …).
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

from starlette.requests import Request

from app.core.config import settings
from app.core.email_identity import identity_email

logger = logging.getLogger(__name__)

_last_sent: dict[str, float] = {}
_report_ip_bucket: dict[str, deque] = defaultdict(deque)


def _cooldown_seconds() -> float:
    return float(getattr(settings, "AUTH_LOGIN_FAILURE_ALERT_COOLDOWN_SECONDS", 180) or 180)


def _normalize_customer_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = identity_email(str(value))
    return v or str(value).strip().lower() or None


def is_customer_login_auth_path(path: str, method: str) -> bool:
    """Chỉ các API đăng nhập/đăng ký khách — không gồm /me, admin-session-token."""
    if not path.startswith("/api/v1/auth"):
        return False
    tail = path[len("/api/v1/auth") :].lstrip("/")
    if tail in ("me",) or tail.startswith("admin-session-token"):
        return False
    m = (method or "GET").upper()
    if tail == "email/verify-magic" and m == "GET":
        return True
    if m != "POST":
        return False
    return tail in (
        "google",
        "send-email-otp",
        "verify-email-otp",
        "email/request",
        "email/verify-otp",
        "report-login-failure",
    )


def _extract_email_from_request(request: Request) -> Optional[str]:
    q = request.query_params.get("email")
    if q:
        return _normalize_customer_email(q)
    scope_email = request.scope.get("auth_alert_email")
    if scope_email:
        return _normalize_customer_email(str(scope_email))
    return None


def _format_detail(detail: Any) -> str:
    if detail is None:
        return "Lỗi không xác định"
    if isinstance(detail, str):
        return detail.strip() or "Lỗi không xác định"
    if isinstance(detail, dict):
        return str(detail.get("detail") or detail.get("message") or detail)[:500]
    if isinstance(detail, list):
        try:
            return json.dumps(detail, ensure_ascii=False)[:500]
        except Exception:
            return str(detail)[:500]
    return str(detail)[:500]


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _prune_cooldown_cache() -> None:
    if len(_last_sent) <= 500:
        return
    cutoff = time.time() - _cooldown_seconds() * 2
    stale = [k for k, t in _last_sent.items() if t < cutoff]
    for k in stale:
        _last_sent.pop(k, None)


def _report_endpoint_rate_limited(client_ip: str) -> bool:
    """Chống spam POST /report-login-failure — tối đa 15 lần / IP / giờ."""
    limit = 15
    window = 3600.0
    t = time.time()
    q = _report_ip_bucket[client_ip]
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(t)
    return False


def _fingerprint(path: str, status_code: int, detail: str, customer_email: Optional[str]) -> str:
    raw = f"{status_code}|{path}|{detail}|{customer_email or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _get_admin_recipient_emails() -> list[str]:
    from app.db.session import SessionLocal
    from app.models.admin import AdminUser

    db = SessionLocal()
    try:
        rows = (
            db.query(AdminUser.email)
            .filter(AdminUser.is_active.is_(True))
            .all()
        )
        seen: set[str] = set()
        out: list[str] = []
        for (email,) in rows:
            e = (email or "").strip().lower()
            if e and "@" in e and e not in seen:
                seen.add(e)
                out.append(e)
        return out
    finally:
        db.close()


def _send_auth_failure_emails_task(
    *,
    path: str,
    method: str,
    status_code: int,
    detail: str,
    customer_email: Optional[str],
    client_ip: str,
) -> None:
    from app.services.email_service import send_email

    if not getattr(settings, "AUTH_LOGIN_FAILURE_ALERT_ENABLED", True):
        return
    if not settings.is_smtp_configured():
        logger.warning("auth_failure_alert skip: SMTP not configured path=%s", path)
        return

    recipients = _get_admin_recipient_emails()
    if not recipients:
        logger.warning("auth_failure_alert skip: no active admin emails")
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    email_line = customer_email or "(chưa có / Google hoặc lỗi trước khi đọc email)"
    subject = "[188] Sự cố đăng nhập khách"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

    text_body = "\n".join(
        [
            "Khách không đăng nhập được trên 188.com.vn.",
            "",
            f"Thời gian: {now}",
            f"API: {method} {path}",
            f"Mã HTTP: {status_code}",
            f"Lý do: {detail}",
            f"Email khách (nếu có): {email_line}",
            f"IP: {client_ip}",
            "",
            "Vui lòng kiểm tra SMTP, Google OAuth, hoặc hỗ trợ khách đăng nhập.",
        ]
    )
    safe_detail = html.escape(detail)
    safe_email = html.escape(email_line)
    safe_path = html.escape(f"{method} {path}")
    safe_ip = html.escape(client_ip)
    html_body = (
        "<p><strong>Khách không đăng nhập được</strong> trên 188.com.vn.</p>"
        f"<p><strong>Thời gian:</strong> {html.escape(now)}<br>"
        f"<strong>API:</strong> {safe_path}<br>"
        f"<strong>Mã HTTP:</strong> {status_code}<br>"
        f"<strong>Lý do:</strong> {safe_detail}<br>"
        f"<strong>Email khách:</strong> {safe_email}<br>"
        f"<strong>IP:</strong> {safe_ip}</p>"
        "<p>Vui lòng kiểm tra SMTP, Google OAuth, hoặc hỗ trợ khách.</p>"
    )

    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
            logger.info("auth_failure_alert sent to=%s path=%s status=%s", addr, path, status_code)
        except Exception:
            logger.exception("auth_failure_alert failed to=%s path=%s", addr, path)


def maybe_notify_auth_login_failure(
    request: Request,
    *,
    status_code: int,
    detail: Any,
) -> None:
    path = request.url.path
    method = request.method
    if status_code < 400 or not is_customer_login_auth_path(path, method):
        return
    if not getattr(settings, "AUTH_LOGIN_FAILURE_ALERT_ENABLED", True):
        return

    detail_str = _format_detail(detail)
    customer_email = _extract_email_from_request(request)
    client_ip = _client_ip(request)
    tail = path[len("/api/v1/auth") :].lstrip("/") if path.startswith("/api/v1/auth") else ""
    if tail == "report-login-failure" and _report_endpoint_rate_limited(client_ip):
        logger.warning("auth_failure_alert skip: report-login-failure rate limited ip=%s", client_ip)
        return

    fp = _fingerprint(path, status_code, detail_str, customer_email)
    now = time.time()
    if now - _last_sent.get(fp, 0.0) < _cooldown_seconds():
        return
    _last_sent[fp] = now
    _prune_cooldown_cache()

    threading.Thread(
        target=_send_auth_failure_emails_task,
        kwargs={
            "path": path,
            "method": method,
            "status_code": status_code,
            "detail": detail_str,
            "customer_email": customer_email,
            "client_ip": client_ip,
        },
        daemon=True,
    ).start()


async def capture_auth_request_context(request: Request) -> Request:
    """Lưu email từ body POST đăng nhập để exception handler dùng."""
    if request.method != "POST" or not is_customer_login_auth_path(request.url.path, "POST"):
        return request
    body = await request.body()
    email: Optional[str] = None
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            raw = data.get("email")
            if raw:
                email = _normalize_customer_email(str(raw))
    except Exception:
        pass
    if email:
        request.scope["auth_alert_email"] = email

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(request.scope, receive)
