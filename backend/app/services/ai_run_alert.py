"""Email admin khi model AI không chạy. Lỗi còn đó thì gửi lại mỗi 24 giờ."""
from __future__ import annotations

import html
import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)


class AiApiStopped(RuntimeError):
    """API AI không chạy. Job phải dừng, không gọi tiếp."""

_LOCK = threading.Lock()
_RESEND_AFTER = timedelta(hours=24)
_KEY_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{10,}|sk-[A-Za-z0-9]{10,}|Bearer\s+\S+)", re.I)


def alert_is_due(sent_at: str, now: datetime) -> bool:
    raw = (sent_at or "").strip()
    if not raw:
        return True
    try:
        sent = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if sent.tzinfo is None:
        sent = sent.replace(tzinfo=timezone.utc)
    return now - sent >= _RESEND_AFTER


def _state_path() -> Path:
    root = Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / "ai_run_alerts.json"


def _load() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"open": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"open": {}}
    if not isinstance(data, dict):
        return {"open": {}}
    data.setdefault("open", {})
    return data


def _save(state: Dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _redact(detail: str) -> str:
    return _KEY_RE.sub("[key]", (detail or "").strip())[:800]


def _site_label() -> str:
    return "188.com.vn"


def _recipients() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in getattr(settings, "VPS_BACKUP_NOTIFY_EMAILS", None) or []:
        email = str(raw).strip().lower()
        if email and "@" in email and email not in seen:
            seen.add(email)
            out.append(email)
    try:
        from app.services.auth_failure_alert import _get_admin_recipient_emails

        for addr in _get_admin_recipient_emails():
            email = (addr or "").strip().lower()
            if email and "@" in email and email not in seen:
                seen.add(email)
                out.append(email)
    except Exception as exc:
        logger.warning("ai_run_alert: không đọc email admin (%s)", exc)
    return out


def _send(model: str, detail: str) -> None:
    if not settings.is_smtp_configured():
        logger.warning("ai_run_alert skip: SMTP chưa cấu hình model=%s", model)
        return
    recipients = _recipients()
    if not recipients:
        logger.warning("ai_run_alert skip: không có email admin model=%s", model)
        return
    from app.services.email_service import send_email

    site = _site_label()
    subject = f"[{site}] Model AI không chạy: {model}"
    text_body = (
        f"Model {model} không chạy được.\n\n"
        f"Lỗi: {detail}\n\n"
        "Cần xử lý: kiểm tra API key, credit hoặc billing của model này.\n"
        "Job đang dùng model này đã dừng, không gọi tiếp.\n"
        "Sau 24 giờ hệ thống thử lại một lần. Còn lỗi thì gửi lại email này.\n"
    )
    html_body = (
        f"<p>Model <b>{html.escape(model)}</b> không chạy được.</p>"
        f"<p>Lỗi: {html.escape(detail)}</p>"
        "<p>Cần xử lý: kiểm tra API key, credit hoặc billing của model này.</p>"
        "<p>Job đang dùng model này đã dừng, không gọi tiếp. "
        "Sau 24 giờ hệ thống thử lại một lần.</p>"
    )
    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
        except Exception:
            logger.exception("ai_run_alert failed model=%s to=%s", model, addr)


def _same_ai(needle: str, name: str) -> bool:
    left = needle.strip().lower()
    right = name.strip().lower()
    if not left:
        return True
    if left in right or right in left:
        return True
    return any(token in left and token in right for token in ("gemini", "openai", "deepseek", "vision"))


def ai_is_paused(name_part: str = "") -> bool:
    """Còn lỗi chưa xử lý trong 24 giờ thì không gọi API lại."""
    needle = (name_part or "").strip().lower()
    now = datetime.now(timezone.utc)
    with _LOCK:
        issues = _load().get("open") or {}
    if not isinstance(issues, dict):
        return False
    for name, row in issues.items():
        if needle and not _same_ai(needle, str(name)):
            continue
        if isinstance(row, dict) and not alert_is_due(str(row.get("sent_at") or ""), now):
            return True
    return False


def notify_ai_down(model: str, detail: str) -> None:
    name = (model or "AI").strip() or "AI"
    message = _redact(detail) or "Không rõ lỗi"
    now = datetime.now(timezone.utc)
    with _LOCK:
        state = _load()
        issues = state.setdefault("open", {})
        row = issues.get(name) if isinstance(issues.get(name), dict) else {}
        if not alert_is_due(str(row.get("sent_at") or ""), now):
            row["detail"] = message
            row["seen_at"] = now.isoformat()
            issues[name] = row
            _save(state)
            return
        issues[name] = {"detail": message, "sent_at": now.isoformat(), "seen_at": now.isoformat()}
        _save(state)
    threading.Thread(target=_send, args=(name, message), daemon=True).start()


def mark_ai_ok(model: str) -> None:
    name = (model or "").strip()
    if not name:
        return
    with _LOCK:
        state = _load()
        issues = state.get("open") or {}
        removed = [key for key in list(issues) if _same_ai(name, str(key))]
        if not removed:
            return
        for key in removed:
            issues.pop(key, None)
        state["open"] = issues
        _save(state)


def raise_ai_stopped(model: str, detail: str) -> None:
    """Báo admin rồi dừng. Không trả về."""
    notify_ai_down(model, detail)
    raise AiApiStopped(f"AI_API_STOPPED {model}: {detail}")
