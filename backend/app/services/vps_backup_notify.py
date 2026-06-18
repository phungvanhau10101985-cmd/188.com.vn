"""Email thông báo admin sau mỗi lần backup VPS."""

from __future__ import annotations

import html
import logging
import threading
from datetime import datetime, timezone
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _notify_enabled() -> bool:
    return getattr(settings, "VPS_BACKUP_NOTIFY_ENABLED", True)


def _recipient_emails() -> List[str]:
    seen: set[str] = set()
    out: list[str] = []

    extra = getattr(settings, "VPS_BACKUP_NOTIFY_EMAILS", None) or []
    for raw in extra:
        e = str(raw).strip().lower()
        if e and "@" in e and e not in seen:
            seen.add(e)
            out.append(e)

    try:
        from app.services.auth_failure_alert import _get_admin_recipient_emails

        for addr in _get_admin_recipient_emails():
            e = (addr or "").strip().lower()
            if e and "@" in e and e not in seen:
                seen.add(e)
                out.append(e)
    except Exception as exc:
        logger.warning("vps_backup_notify: không đọc email admin từ DB (%s)", exc)
    return out


def _send_email_task(
    *,
    run_id: int,
    status: str,
    trigger: str,
    archive_filename: Optional[str],
    archive_size_pretty: Optional[str],
    error_message: Optional[str],
    drive_upload_status: Optional[str] = None,
    drive_web_link: Optional[str] = None,
    drive_upload_error: Optional[str] = None,
) -> None:
    if not _notify_enabled():
        return
    recipients = _recipient_emails()
    if not recipients:
        logger.warning("vps_backup_notify skip: không có email admin")
        return
    if not settings.is_smtp_configured():
        logger.warning("vps_backup_notify skip: SMTP chưa cấu hình")
        return

    from app.services.email_service import send_email

    ok = status == "success"
    subject = f"[188.com.vn] Backup VPS {'thành công' if ok else 'thất bại'} #{run_id}"
    src = "Lịch tự động" if trigger == "scheduled" else "Thủ công"
    finished = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    file_line = archive_filename or "—"
    size_line = archive_size_pretty or "—"
    err_line = (error_message or "").strip() or "—"

    text_body = (
        f"Backup VPS — {subject}\n\n"
        f"Nguồn: {src}\n"
        f"Trạng thái: {status}\n"
        f"File: {file_line}\n"
        f"Dung lượng: {size_line}\n"
        f"Thời gian: {finished}\n"
    )
    if not ok:
        text_body += f"Lỗi: {err_line}\n"
    if drive_upload_status == "success" and drive_web_link:
        text_body += f"\nGoogle Drive: {drive_web_link}\n"
    elif drive_upload_status == "failed":
        text_body += f"\nGoogle Drive: thất bại — {(drive_upload_error or '').strip() or '—'}\n"
    text_body += "\nTải file: Admin → Backup VPS → Tải xuống\n"

    heading_color = "#15803d" if ok else "#b91c1c"
    html_parts = [
        '<div style="font-family:Arial,sans-serif;font-size:14px;color:#111">',
        f'<h2 style="color:{heading_color}">{html.escape(subject)}</h2>',
        f"<p><b>Nguồn:</b> {html.escape(src)}</p>",
        f"<p><b>Trạng thái:</b> {html.escape(status)}</p>",
        f"<p><b>File:</b> <code>{html.escape(file_line)}</code></p>",
        f"<p><b>Dung lượng:</b> {html.escape(size_line)}</p>",
        f"<p><b>Thời gian:</b> {html.escape(finished)}</p>",
    ]
    if not ok:
        html_parts.append(f"<p><b>Lỗi:</b> {html.escape(err_line)}</p>")
    if drive_upload_status == "success" and drive_web_link:
        link = html.escape(drive_web_link)
        html_parts.append(f'<p><b>Google Drive:</b> <a href="{link}">Mở file trên Drive</a></p>')
    elif drive_upload_status == "failed":
        drive_err = html.escape((drive_upload_error or "Upload thất bại").strip())
        html_parts.append(
            f'<p><b>Google Drive:</b> <span style="color:#b91c1c">{drive_err}</span></p>'
        )
    html_parts.append(
        "<p>Vào <b>Quản trị → Backup VPS</b> để tải file hoặc xem nhật ký.</p>"
    )
    html_parts.append("</div>")
    html_body = "\n      ".join(html_parts)

    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
        except Exception:
            logger.exception("vps_backup_notify failed to=%s run_id=%s", addr, run_id)


def notify_backup_finished(
    *,
    run_id: int,
    status: str,
    trigger: str,
    archive_filename: Optional[str] = None,
    archive_size_pretty: Optional[str] = None,
    error_message: Optional[str] = None,
    drive_upload_status: Optional[str] = None,
    drive_web_link: Optional[str] = None,
    drive_upload_error: Optional[str] = None,
) -> None:
    threading.Thread(
        target=_send_email_task,
        kwargs={
            "run_id": run_id,
            "status": status,
            "trigger": trigger,
            "archive_filename": archive_filename,
            "archive_size_pretty": archive_size_pretty,
            "error_message": error_message,
            "drive_upload_status": drive_upload_status,
            "drive_web_link": drive_web_link,
            "drive_upload_error": drive_upload_error,
        },
        daemon=True,
        name=f"vps-backup-email-{run_id}",
    ).start()
