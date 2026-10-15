"""Báo lỗi từ web + trang admin Quản lý lỗi."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import require_privileged_admin
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.site_error_log import SiteErrorLog
from app.services.site_error_log import (
    record_site_error,
    resolve_report_source,
    stack_signature,
    vn_today,
)

router = APIRouter()

_report_hits: dict[str, deque] = defaultdict(deque)
_REPORT_LIMIT = 30
_REPORT_WINDOW = 60.0


class SiteErrorReportBody(BaseModel):
    message: str = ""
    stack: str = ""
    path: str = ""
    digest: str = ""
    kind: str = ""


class SiteErrorResolveBody(BaseModel):
    resolved: bool = Field(...)


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else ""
    if peer in {"127.0.0.1", "::1"}:
        xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if xff:
            return xff[:64]
    return (peer or "")[:64]


_daily_reports: dict[str, tuple[str, int]] = {}
_DAILY_REPORT_CAP = 100


def _limited(ip: str) -> bool:
    now = time.time()
    key = ip or "unknown"
    bucket = _report_hits[key]
    while bucket and now - bucket[0] > _REPORT_WINDOW:
        bucket.popleft()
    if len(bucket) >= _REPORT_LIMIT:
        return True
    bucket.append(now)
    day = vn_today().isoformat()
    current = _daily_reports.get(key)
    count = current[1] if current and current[0] == day else 0
    if count >= _DAILY_REPORT_CAP:
        return True
    _daily_reports[key] = (day, count + 1)
    if len(_daily_reports) > 5000:
        _daily_reports.clear()
    return False


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _row_out(row: SiteErrorLog, *, with_detail: bool) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "level": row.level,
        "logger_name": row.logger_name or "",
        "exc_type": row.exc_type or "",
        "message": row.message or "",
        "path": row.path or "",
        "method": row.method or "",
        "status_code": row.status_code,
        "occurrence_count": int(row.occurrence_count or 1),
        "first_seen_at": _iso(row.first_seen_at),
        "last_seen_at": _iso(row.last_seen_at),
        "email_sent_at": _iso(row.email_sent_at),
        "resolved": bool(row.resolved),
        "log_day": row.log_day.isoformat() if row.log_day else None,
        "detail": (row.detail or "") if with_detail else None,
        "user_agent": (row.user_agent or "") if with_detail else None,
        "client_ip": (row.client_ip or "") if with_detail else None,
    }


@router.post("/report", status_code=204)
def report_site_error(
    body: SiteErrorReportBody,
    request: Request,
    x_site_error_token: str = Header(default=""),
):
    """Trình duyệt và Next server gửi lỗi. Không cần đăng nhập."""
    ip = _client_ip(request)
    if _limited(ip):
        return Response(status_code=204)
    message = (body.message or "").strip()
    digest = (body.digest or "").strip()
    if digest and digest not in message:
        message = f"{message} [digest:{digest[:40]}]".strip()
    if not message:
        return Response(status_code=204)
    source = resolve_report_source(kind=body.kind, token=x_site_error_token)
    stack = (body.stack or "")[:8000]
    path = (body.path or "")[:500] or (request.headers.get("referer") or "")[:500]
    payload = dict(
        source=source,
        message=message[:2000],
        detail=stack,
        location=stack_signature(stack) or path,
        path=path,
        method=(request.method or "")[:12],
        user_agent=(request.headers.get("user-agent") or "")[:300],
        client_ip=ip,
        logger_name="next" if source == "web_server" else "browser",
        exc_type=digest[:160] if source == "web_server" and digest else "",
    )
    try:
        if source == "web_server":
            # Email SMTP không được chặn response lỗi của Next.
            threading.Thread(
                target=record_site_error,
                kwargs=payload,
                name="site-error-web-server",
                daemon=True,
            ).start()
        else:
            record_site_error(**payload)
    except Exception:
        return Response(status_code=204)
    return Response(status_code=204)


@router.get("")
def list_site_errors(
    days: int = Query(7, ge=1, le=90),
    source: str = Query(""),
    status: str = Query("open"),
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    from datetime import timedelta

    today = vn_today()
    cutoff = today - timedelta(days=days - 1)
    query = db.query(SiteErrorLog).filter(SiteErrorLog.log_day >= cutoff)
    src = (source or "").strip().lower()
    if src in {"server", "web", "web_server"}:
        query = query.filter(SiteErrorLog.source == src)
    state = (status or "open").strip().lower()
    if state == "open":
        query = query.filter(SiteErrorLog.resolved.is_(False))
    elif state == "done":
        query = query.filter(SiteErrorLog.resolved.is_(True))
    text = (q or "").strip()[:80]
    if text:
        like = f"%{text}%"
        query = query.filter(
            SiteErrorLog.message.ilike(like) | SiteErrorLog.path.ilike(like)
        )
    total = query.count()
    rows = (
        query.order_by(SiteErrorLog.last_seen_at.desc(), SiteErrorLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    today_q = db.query(SiteErrorLog).filter(SiteErrorLog.log_day == today)
    today_occurrences = (
        db.query(func.coalesce(func.sum(SiteErrorLog.occurrence_count), 0))
        .filter(SiteErrorLog.log_day == today)
        .scalar()
    )
    return {
        "items": [_row_out(row, with_detail=False) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {
            "today_errors": today_q.count(),
            "today_occurrences": int(today_occurrences or 0),
            "today_emails": today_q.filter(SiteErrorLog.email_sent_at.isnot(None)).count(),
            "open_count": db.query(SiteErrorLog).filter(SiteErrorLog.resolved.is_(False)).count(),
        },
    }


@router.get("/{error_id}")
def get_site_error(
    error_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    row = db.query(SiteErrorLog).filter(SiteErrorLog.id == error_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lỗi")
    return _row_out(row, with_detail=True)


@router.patch("/{error_id}")
def update_site_error(
    error_id: int,
    body: SiteErrorResolveBody,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(require_privileged_admin),
):
    row = db.query(SiteErrorLog).filter(SiteErrorLog.id == error_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lỗi")
    row.resolved = bool(body.resolved)
    db.commit()
    db.refresh(row)
    return _row_out(row, with_detail=True)
