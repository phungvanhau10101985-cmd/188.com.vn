"""
Ghi mọi lỗi web và log server (ERROR+).

Email admin chỉ cho lỗi server / web server. Cùng một lỗi (fingerprint) trong một ngày
giờ Việt Nam gửi tối đa một lần.
"""

from __future__ import annotations

import contextvars
import hashlib
import hmac
import html
import logging
import queue
import re
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))
EMAIL_SOURCES = frozenset({"server", "web_server"})
_MESSAGE_LIMIT = 2000
_DETAIL_LIMIT = 8000
_RETAIN_DAYS = 30
_QUEUE_MAX = 2000
_COALESCE_SEC = 1.0
_EMAIL_RETRY_SEC = 3600.0

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_NUM_RE = re.compile(r"\b\d{2,}\b")
_WS_RE = re.compile(r"\s+")
_PATH_ID_RE = re.compile(r"/\d+")
_CLIENT_NOISE = (
    "resizeobserver loop",
    "script error.",
    "chrome-extension://",
    "moz-extension://",
    "safari-web-extension://",
    "aborterror",
    "the operation was aborted",
    "the user aborted a request",
    # Trình duyệt nhúng Facebook/Instagram/Zalo và tab cũ sau deploy — không phải lỗi app.
    "java object is gone",
    "webkit.messagehandlers",
    "zalojsv2",
    "loading chunk",
    "chunkloaderror",
    "failed to read the 'localstorage' property",
    "access is denied for this document",
)

_table_ready = False
_table_lock = threading.Lock()
_last_prune_at = 0.0
_prune_lock = threading.Lock()
_email_backoff: dict[str, float] = {}
# ContextVar cho request async — logging handler đọc trên cùng task.
_http_ctx: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "site_error_http",
    default={},
)

_QUEUE: "queue.Queue[Optional[dict[str, Any]]]" = queue.Queue(maxsize=_QUEUE_MAX)
_worker_started = False
_worker_lock = threading.Lock()
_emit_local = threading.local()
_coalesce_lock = threading.Lock()
_last_queued: dict[str, float] = {}
_pending_repeats: dict[str, int] = {}


def vn_today(now: Optional[datetime] = None):
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(VN_TZ).date()


def normalize_error_text(text: str) -> str:
    s = _UUID_RE.sub("#", text or "")
    s = _NUM_RE.sub("#", s)
    s = _WS_RE.sub(" ", s).strip().lower()
    return s[:400]


def normalize_path(path: str) -> str:
    p = (path or "").split("?")[0].strip()
    p = _UUID_RE.sub("#", p)
    p = _PATH_ID_RE.sub("/#", p)
    return p[:180]


def stack_signature(stack: str) -> str:
    for line in (stack or "").splitlines():
        raw = line.strip()
        if not raw or raw.lower().startswith("error:"):
            continue
        raw = re.sub(r":\d+:\d+", "", raw)
        raw = re.sub(r"\?[^)\s]*", "", raw)
        return raw[:180]
    return ""


def build_fingerprint(*, source: str, exc_type: str, location: str, message: str) -> str:
    raw = "|".join(
        [
            (source or "").strip().lower(),
            (exc_type or "").strip().lower(),
            (location or "").strip().lower(),
            normalize_error_text(message),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def is_client_noise(message: str, stack: str = "") -> bool:
    blob = f"{message}\n{stack}".lower()
    return any(needle in blob for needle in _CLIENT_NOISE)


def ingest_secret() -> str:
    explicit = (getattr(settings, "SITE_ERROR_INGEST_SECRET", "") or "").strip()
    if explicit:
        return explicit
    return (getattr(settings, "CRON_SECRET", "") or "").strip()


def secret_matches(token: str) -> bool:
    expected = ingest_secret()
    got = (token or "").strip()
    if not expected or not got:
        return False
    try:
        return hmac.compare_digest(got.encode("utf-8"), expected.encode("utf-8"))
    except Exception:
        return False


def resolve_report_source(*, kind: str, token: str) -> str:
    if secret_matches(token) and (kind or "").strip() == "web_server":
        return "web_server"
    return "web"


def should_capture_record(record: logging.LogRecord) -> bool:
    if record.levelno < logging.ERROR:
        return False
    name = record.name or ""
    if name.startswith("app.services.site_error_log"):
        return False
    try:
        msg = record.getMessage()
    except Exception:
        return False
    if name.startswith("uvicorn") and "Exception in ASGI application" in msg:
        return False
    # Pool trả connection đã bị Postgres cắt — hệ quả của idle-in-transaction, không phải lỗi mới.
    if name.startswith("sqlalchemy.pool") and "Exception during reset" in msg:
        return False
    return True


def _location_from_tb(tb) -> str:
    last = None
    app_frame = None
    while tb is not None:
        last = tb
        fn = (tb.tb_frame.f_code.co_filename or "").replace("\\", "/")
        if "/app/" in fn or fn.endswith("/main.py"):
            app_frame = tb
        tb = tb.tb_next
    chosen = app_frame or last
    if chosen is None:
        return ""
    fn = (chosen.tb_frame.f_code.co_filename or "").replace("\\", "/")
    if "/app/" in fn:
        short = "app/" + fn.split("/app/", 1)[1]
    elif "/backend/" in fn:
        short = fn.split("/backend/", 1)[1]
    else:
        short = fn
    return f"{short}:{chosen.tb_lineno}"


def _location_from_record(record: logging.LogRecord) -> str:
    if record.exc_info and record.exc_info[2] is not None:
        loc = _location_from_tb(record.exc_info[2])
        if loc:
            return loc
    pathname = (record.pathname or "").replace("\\", "/")
    if "/app/" in pathname:
        pathname = "app/" + pathname.split("/app/", 1)[1]
    return f"{pathname}:{record.lineno}"


def _exc_type_from_record(record: logging.LogRecord) -> str:
    if record.exc_info and record.exc_info[0] is not None:
        return record.exc_info[0].__name__
    return ""


def _detail_from_record(record: logging.LogRecord) -> str:
    if not record.exc_info or record.exc_info[0] is None:
        return ""
    try:
        text = "".join(traceback.format_exception(*record.exc_info))
    except Exception:
        return ""
    return text[:_DETAIL_LIMIT]


def current_http_context() -> dict[str, str]:
    try:
        ctx = _http_ctx.get()
    except LookupError:
        ctx = {}
    return dict(ctx or {})


def ensure_site_error_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with _table_lock:
        if _table_ready:
            return
        from app.db.session import engine
        from app.models.site_error_log import SiteErrorLog

        SiteErrorLog.__table__.create(bind=engine, checkfirst=True)
        _table_ready = True


def _maybe_prune(db: Session, today) -> None:
    global _last_prune_at
    now_ts = time.time()
    with _prune_lock:
        if now_ts - _last_prune_at < 3600:
            return
        _last_prune_at = now_ts
    cutoff = today - timedelta(days=_RETAIN_DAYS)
    from app.models.site_error_log import SiteErrorLog

    db.query(SiteErrorLog).filter(SiteErrorLog.log_day < cutoff).delete(synchronize_session=False)


def _alerts_enabled() -> bool:
    return bool(getattr(settings, "SITE_ERROR_ALERT_ENABLED", True))


def _admin_recipients() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(addr: str) -> None:
        e = (addr or "").strip().lower()
        if e and "@" in e and e not in seen:
            seen.add(e)
            out.append(e)

    for raw in getattr(settings, "OPS_HEALTH_ALERT_EMAILS", None) or []:
        add(str(raw))

    try:
        from app.db.session import SessionLocal
        from app.models.admin import AdminRole, AdminUser

        db = SessionLocal()
        try:
            privileged = (
                db.query(AdminUser.email)
                .filter(
                    AdminUser.is_active.is_(True),
                    AdminUser.role.in_([AdminRole.SUPER_ADMIN, AdminRole.ADMIN]),
                )
                .all()
            )
            rows = privileged
            if not rows:
                rows = db.query(AdminUser.email).filter(AdminUser.is_active.is_(True)).all()
            for (email,) in rows:
                add(email or "")
        finally:
            db.close()
    except Exception:
        logger.warning("site_error: không đọc được email admin", exc_info=True)
    return out


def _website_base() -> str:
    base = (getattr(settings, "WEBSITE_URL", "") or "").strip().rstrip("/")
    return base or "https://188.com.vn"


def _deliver_alert(row, *, now: datetime) -> bool:
    if not _alerts_enabled():
        return False
    if not settings.is_smtp_configured():
        logger.warning("site_error email skip: SMTP chưa cấu hình")
        return False
    recipients = _admin_recipients()
    if not recipients:
        logger.warning("site_error email skip: không có email admin")
        return False

    from app.services.email_service import send_email

    when = now.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M")
    message = (row.message or "").strip()
    short = " ".join(message.split())[:90] or "Lỗi server"
    subject = f"[188] Lỗi server: {short}"
    prefix = (getattr(settings, "EMAIL_SUBJECT_PREFIX", "") or "").strip()
    if prefix:
        subject = f"{prefix} {subject}"
    link = f"{_website_base()}/admin/errors?id={row.id}"
    source_label = "Server web (Next.js)" if row.source == "web_server" else "API / server log"
    path_line = f"{(row.method or '').strip()} {(row.path or '').strip()}".strip() or "(không có)"
    detail = (row.detail or "").strip()
    if len(detail) > 3500:
        detail = detail[:3500] + "\n…"
    count = int(row.occurrence_count or 1)
    text_body = "\n".join(
        [
            "Có lỗi trên 188.com.vn.",
            "",
            f"Thời gian: {when} (giờ Việt Nam)",
            f"Nguồn: {source_label}",
            f"Logger: {row.logger_name or '-'}",
            f"Đường dẫn: {path_line}",
            f"Số lần trong ngày: {count}",
            "",
            "Nội dung:",
            message,
            "",
            "Chi tiết:",
            detail or "(không có stack)",
            "",
            f"Xem trong admin: {link}",
            "",
            "Cùng một lỗi chỉ gửi email tối đa một lần mỗi ngày.",
        ]
    )
    html_body = (
        "<p><strong>Có lỗi trên 188.com.vn.</strong></p>"
        f"<p><strong>Thời gian:</strong> {html.escape(when)} (giờ Việt Nam)<br>"
        f"<strong>Nguồn:</strong> {html.escape(source_label)}<br>"
        f"<strong>Logger:</strong> {html.escape(row.logger_name or '-')}<br>"
        f"<strong>Đường dẫn:</strong> {html.escape(path_line)}<br>"
        f"<strong>Số lần trong ngày:</strong> {count}</p>"
        f"<p><strong>Nội dung:</strong><br><pre style=\"white-space:pre-wrap\">{html.escape(message)}</pre></p>"
        f"<p><strong>Chi tiết:</strong><br><pre style=\"white-space:pre-wrap\">{html.escape(detail or '(không có stack)')}</pre></p>"
        f"<p><a href=\"{html.escape(link)}\">Mở Quản lý lỗi</a></p>"
        "<p>Cùng một lỗi chỉ gửi email tối đa một lần mỗi ngày.</p>"
    )
    ok = False
    for addr in recipients:
        try:
            if send_email(addr, subject, text_body, html_body, prevent_threading=True):
                ok = True
        except Exception:
            logger.warning("site_error email failed to=%s", addr, exc_info=True)
    return ok


def _email_if_first_today(db: Session, row, *, now: datetime) -> bool:
    from sqlalchemy import update

    from app.models.site_error_log import SiteErrorLog

    fp = row.fingerprint or ""
    if time.time() < _email_backoff.get(fp, 0):
        return False
    if row.email_sent_at is not None:
        return False
    claimed = db.execute(
        update(SiteErrorLog)
        .where(SiteErrorLog.id == row.id, SiteErrorLog.email_sent_at.is_(None))
        .values(email_sent_at=now)
    )
    db.commit()
    if (claimed.rowcount or 0) < 1:
        return False
    ok = False
    try:
        db.refresh(row)
        ok = _deliver_alert(row, now=now)
    except Exception:
        logger.warning("site_error deliver failed id=%s", row.id, exc_info=True)
        ok = False
    if ok:
        return True
    db.execute(
        update(SiteErrorLog).where(SiteErrorLog.id == row.id).values(email_sent_at=None)
    )
    db.commit()
    _email_backoff[fp] = time.time() + _EMAIL_RETRY_SEC
    return False


def record_site_error(
    *,
    source: str,
    message: str,
    exc_type: str = "",
    location: str = "",
    detail: str = "",
    logger_name: str = "",
    path: str = "",
    method: str = "",
    status_code: Optional[int] = None,
    user_agent: str = "",
    client_ip: str = "",
    level: str = "error",
    fingerprint: str = "",
    extra_count: int = 0,
    db: Optional[Session] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    source = (source or "server").strip().lower()
    if source not in {"server", "web", "web_server"}:
        source = "web"
    message = (message or "").strip()[:_MESSAGE_LIMIT]
    if not message:
        return {"skipped": True}
    if source == "web" and is_client_noise(message, detail):
        return {"skipped": True}

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    day = vn_today(moment)
    fp = fingerprint or build_fingerprint(
        source=source,
        exc_type=exc_type,
        location=location,
        message=message,
    )
    bump = 1 + max(0, int(extra_count or 0))
    own = db is None
    if own:
        try:
            ensure_site_error_table()
        except Exception:
            logger.warning("site_error: không tạo được bảng", exc_info=True)
            return {"skipped": True}
        from app.db.session import SessionLocal

        db = SessionLocal()

    from app.models.site_error_log import SiteErrorLog

    assert db is not None
    try:
        _maybe_prune(db, day)
        row = (
            db.query(SiteErrorLog)
            .filter(
                SiteErrorLog.fingerprint == fp,
                SiteErrorLog.log_day == day,
                SiteErrorLog.source == source,
            )
            .one_or_none()
        )
        created = False
        if row is None:
            row = SiteErrorLog(
                fingerprint=fp,
                log_day=day,
                source=source,
                level=(level or "error")[:20],
                logger_name=(logger_name or "")[:160] or None,
                exc_type=(exc_type or "")[:160] or None,
                message=message,
                detail=(detail or "")[:_DETAIL_LIMIT] or None,
                path=(path or "")[:500] or None,
                method=(method or "")[:12] or None,
                status_code=status_code,
                user_agent=(user_agent or "")[:300] or None,
                client_ip=(client_ip or "")[:64] or None,
                occurrence_count=bump,
                first_seen_at=moment,
                last_seen_at=moment,
                resolved=False,
            )
            db.add(row)
            try:
                db.commit()
                created = True
            except IntegrityError:
                db.rollback()
                row = (
                    db.query(SiteErrorLog)
                    .filter(
                        SiteErrorLog.fingerprint == fp,
                        SiteErrorLog.log_day == day,
                        SiteErrorLog.source == source,
                    )
                    .one()
                )
        if not created and row is not None:
            row.occurrence_count = int(row.occurrence_count or 0) + bump
            row.last_seen_at = moment
            row.message = message
            if detail:
                row.detail = detail[:_DETAIL_LIMIT]
            if path:
                row.path = path[:500]
            if method:
                row.method = method[:12]
            if logger_name:
                row.logger_name = logger_name[:160]
            if exc_type:
                row.exc_type = exc_type[:160]
            if user_agent:
                row.user_agent = user_agent[:300]
            if client_ip:
                row.client_ip = client_ip[:64]
            if row.resolved:
                row.resolved = False
            db.commit()
        db.refresh(row)
        emailed = False
        if source in EMAIL_SOURCES:
            emailed = _email_if_first_today(db, row, now=moment)
        return {
            "id": row.id,
            "fingerprint": fp,
            "occurrence_count": int(row.occurrence_count or 1),
            "emailed": emailed,
            "skipped": False,
        }
    except Exception:
        db.rollback()
        logger.warning("site_error: ghi lỗi thất bại", exc_info=True)
        return {"skipped": True}
    finally:
        if own:
            db.close()


def _drain_repeats(fp: str) -> int:
    with _coalesce_lock:
        return int(_pending_repeats.pop(fp, 0) or 0)


def _enqueue_log_record(record: logging.LogRecord) -> None:
    if getattr(_emit_local, "busy", False):
        return
    if not should_capture_record(record):
        return
    try:
        log_msg = record.getMessage()
    except Exception:
        return
    log_msg = (log_msg or "").strip()
    if not log_msg:
        return
    exc_type = _exc_type_from_record(record)
    if exc_type and exc_type not in log_msg:
        message = f"{exc_type}: {log_msg}"
    else:
        message = log_msg
    location = _location_from_record(record)
    ctx = current_http_context()
    path = (ctx.get("path") or "")[:500]
    method = (ctx.get("method") or "")[:12]
    fp = build_fingerprint(
        source="server",
        exc_type=exc_type,
        location=location,
        message=message,
    )
    now_ts = time.time()
    with _coalesce_lock:
        last = _last_queued.get(fp, 0.0)
        if now_ts - last < _COALESCE_SEC:
            _pending_repeats[fp] = int(_pending_repeats.get(fp, 0) or 0) + 1
            return
        _last_queued[fp] = now_ts
        if len(_last_queued) > 500:
            cutoff = now_ts - 120
            for key, ts in list(_last_queued.items()):
                if ts < cutoff:
                    _last_queued.pop(key, None)
        extra = int(_pending_repeats.pop(fp, 0) or 0)
    payload = {
        "source": "server",
        "message": message[:_MESSAGE_LIMIT],
        "exc_type": exc_type,
        "location": location,
        "detail": _detail_from_record(record),
        "logger_name": (record.name or "")[:160],
        "path": path,
        "method": method,
        "user_agent": (ctx.get("user_agent") or "")[:300],
        "client_ip": (ctx.get("client_ip") or "")[:64],
        "fingerprint": fp,
        "extra_count": extra,
    }
    try:
        _QUEUE.put_nowait(payload)
    except queue.Full:
        return
    _start_worker()


class SiteErrorLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _enqueue_log_record(record)
        except Exception:
            return


def _worker_loop() -> None:
    while True:
        item = _QUEUE.get()
        if item is None:
            _QUEUE.task_done()
            return
        _emit_local.busy = True
        try:
            time.sleep(_COALESCE_SEC)
            fp = str(item.get("fingerprint") or "")
            item["extra_count"] = int(item.get("extra_count") or 0) + _drain_repeats(fp)
            record_site_error(**item)
        except Exception:
            logger.warning("site_error worker failed", exc_info=True)
        finally:
            _emit_local.busy = False
            _QUEUE.task_done()


def _start_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker_loop, name="site-error-log", daemon=True)
        thread.start()
        _worker_started = True


def install_site_error_logging() -> None:
    """Gắn lại handler nếu uvicorn dictConfig đã gỡ handler lúc import."""
    root = logging.getLogger()
    if not any(isinstance(h, SiteErrorLogHandler) for h in root.handlers):
        handler = SiteErrorLogHandler()
        handler.setLevel(logging.ERROR)
        root.addHandler(handler)
    _start_worker()


class SiteErrorRequestContextMiddleware:
    """Gắn path/method của request để log ERROR trong request có ngữ cảnh."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers: dict[str, str] = {}
        for key, value in scope.get("headers") or []:
            headers[key.decode("latin-1").lower()] = value.decode("utf-8", "ignore")
        client = scope.get("client") or ("", 0)
        peer = str(client[0] or "")
        ip = peer
        if peer in {"127.0.0.1", "::1"}:
            xff = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
            if xff:
                ip = xff
        token = _http_ctx.set(
            {
                "path": str(scope.get("path") or "")[:500],
                "method": str(scope.get("method") or "")[:12],
                "user_agent": (headers.get("user-agent") or "")[:300],
                "client_ip": ip[:64],
            }
        )
        try:
            await self.app(scope, receive, send)
        finally:
            _http_ctx.reset(token)
