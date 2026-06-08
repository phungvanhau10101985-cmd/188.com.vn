"""
Email cảnh báo admin khi VPS/API gặp sự cố nặng (pool DB kẹt, storefront down, job OCR…).

Người nhận: admin_users active + OPS_HEALTH_ALERT_EMAILS (tuỳ chọn).
Cooldown theo loại cảnh báo — tránh spam.
"""
from __future__ import annotations

import html
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_last_sent: dict[str, float] = {}


def _cooldown_seconds() -> float:
    return float(getattr(settings, "OPS_HEALTH_ALERT_COOLDOWN_SECONDS", 900) or 900)


def _alert_enabled() -> bool:
    return getattr(settings, "OPS_HEALTH_ALERT_ENABLED", True)


def _get_recipient_emails(*, allow_db_lookup: bool = True) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    extra = getattr(settings, "OPS_HEALTH_ALERT_EMAILS", None) or []
    for raw in extra:
        e = str(raw).strip().lower()
        if e and "@" in e and e not in seen:
            seen.add(e)
            out.append(e)

    if not allow_db_lookup:
        return out

    try:
        from app.services.auth_failure_alert import _get_admin_recipient_emails

        for addr in _get_admin_recipient_emails():
            e = (addr or "").strip().lower()
            if e and "@" in e and e not in seen:
                seen.add(e)
                out.append(e)
    except Exception as exc:
        logger.warning("ops_health_alert: không đọc được admin từ DB (%s) — dùng OPS_HEALTH_ALERT_EMAILS", exc)
    return out


def collect_heavy_process_hints() -> list[str]:
    """Process hay làm nặng VPS / ăn pool DB (chỉ Linux)."""
    patterns: list[tuple[str, str]] = [
        ("Job OCR / bản địa hóa ảnh", r"image_localization_job|imgloc-|_multiprocess_job_entry"),
        ("Source stock scrape (Playwright)", r"source-stock-checker|check_product_source_stock"),
        ("Deploy build Next", r"npm run build|next build"),
        ("Import Excel / listing queue", r"listing_import_queue|import_export"),
    ]
    hints: list[str] = []
    for label, pattern in patterns:
        try:
            proc = subprocess.run(
                ["pgrep", "-af", pattern],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            line = (proc.stdout or "").strip()
            if line:
                hints.append(f"{label}:\n{line[:350]}")
        except Exception:
            continue
    return hints


def _format_pool_block(pool_snap: Optional[dict]) -> str:
    if not pool_snap:
        return "(không đọc được pool)"
    return (
        f"checked_out={pool_snap.get('checked_out')} / pool_max={pool_snap.get('pool_max')} "
        f"(checked_in={pool_snap.get('checked_in')}, overflow={pool_snap.get('overflow')}, "
        f"near_full={pool_snap.get('near_full')})"
    )


def build_recovery_commands(
    alert_kind: str,
    *,
    heavy_hints: Optional[Iterable[str]] = None,
) -> str:
    """
    Lệnh SSH copy/paste để reset VPS — gửi kèm email admin.
    """
    kind = (alert_kind or "ops").strip().lower()
    heavy_blob = "\n".join(heavy_hints or []).lower()
    has_ocr = "image_localization" in heavy_blob or "imgloc" in heavy_blob or "ocr" in heavy_blob
    has_web_hint = kind in ("storefront_down", "pool_restart")

    lines = [
        "# SSH vào VPS (đổi IP/user nếu khác)",
        "ssh root@14.225.218.39",
        "",
        "# === Reset nhanh — chạy lần lượt ===",
        "cd /var/www/188.com.vn",
        "",
        "# 1) Xem server đang nặng gì",
        "bash deploy/check-server-load.sh",
        "",
        "# 2) Giải phóng pool DB + dừng OCR + restart API sạch (quan trọng nhất)",
        "bash deploy/free-api-now.sh",
        "",
    ]

    if has_ocr:
        lines.extend(
            [
                "# (Tuỳ chọn) Hủy job bản địa hóa ảnh nếu vẫn thấy img loc trong check-server-load",
                "bash deploy/cancel-image-localization-job.sh --all-active --nuke",
                "",
            ]
        )

    lines.extend(
        [
            "# 3) Xác nhận web + API + products OK",
            "bash deploy/health-check.sh",
            "",
        ]
    )

    if has_web_hint:
        lines.extend(
            [
                "# 4) Nếu web Next vẫn lỗi",
                "bash deploy/fix-web-health.sh",
                "",
            ]
        )

    lines.extend(
        [
            "# 5) Log API (nếu health-check vẫn fail)",
            "pm2 logs 188-api --lines 50 --nostream",
            "",
            "# Pull code mới nhất (sau khi dev push)",
            "# git pull origin main && pm2 restart 188-api --update-env && pm2 save",
        ]
    )

    if kind == "pool_restart":
        lines.insert(
            8,
            "# Lưu ý: email này gửi khi API sắp/t vừa tự restart — có thể chỉ cần bước 3 sau ~30s",
        )

    return "\n".join(lines)


def _prune_cooldown_cache() -> None:
    if len(_last_sent) <= 200:
        return
    cutoff = time.time() - _cooldown_seconds() * 2
    for key, ts in list(_last_sent.items()):
        if ts < cutoff:
            _last_sent.pop(key, None)


def _send_ops_alert_email_task(
    *,
    alert_kind: str,
    title: str,
    detail: str,
    pool_snap: Optional[dict] = None,
    heavy_hints: Optional[Iterable[str]] = None,
    action: str = "",
    env_recipients_only: bool = False,
) -> None:
    from app.services.email_service import send_email

    if not _alert_enabled():
        return
    if not settings.is_smtp_configured():
        logger.warning("ops_health_alert skip: SMTP not configured kind=%s", alert_kind)
        return

    recipients = _get_recipient_emails(allow_db_lookup=not env_recipients_only)
    if not recipients and not env_recipients_only:
        recipients = _get_recipient_emails(allow_db_lookup=False)
    if not recipients:
        logger.warning("ops_health_alert skip: no recipients kind=%s (đặt OPS_HEALTH_ALERT_EMAILS trong .env)", alert_kind)
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    heavy_lines = list(heavy_hints or collect_heavy_process_hints())
    heavy_text = "\n\n".join(heavy_lines) if heavy_lines else "(không thấy process nặng rõ ràng — có thể pool leak hoặc traffic SSR cao)"
    pool_line = _format_pool_block(pool_snap)
    recovery_cmds = build_recovery_commands(alert_kind, heavy_hints=heavy_lines)
    action_line = action.strip() or "Chạy block lệnh bên dưới trên VPS (SSH)."

    subject = f"[188] {title}"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

    text_body = "\n".join(
        [
            title,
            "",
            f"Thời gian: {now}",
            f"Loại: {alert_kind}",
            f"Chi tiết: {detail}",
            "",
            f"Pool DB: {pool_line}",
            "",
            "Process / job có thể gây nặng:",
            heavy_text,
            "",
            f"Hành động: {action_line}",
            "",
            "=== LỆNH RESET (copy vào terminal SSH) ===",
            recovery_cmds,
            "",
            "Khách có thể thấy web chậm/treo nếu không chạy reset kịp.",
        ]
    )

    html_body = (
        f"<p><strong>{html.escape(title)}</strong></p>"
        f"<p><strong>Thời gian:</strong> {html.escape(now)}<br>"
        f"<strong>Loại:</strong> {html.escape(alert_kind)}<br>"
        f"<strong>Chi tiết:</strong> {html.escape(detail)}</p>"
        f"<p><strong>Pool DB:</strong> {html.escape(pool_line)}</p>"
        f"<p><strong>Process / job nặng:</strong><br><pre style=\"white-space:pre-wrap\">"
        f"{html.escape(heavy_text)}</pre></p>"
        f"<p><strong>Hành động:</strong> {html.escape(action_line)}</p>"
        f"<p><strong>Lệnh reset trên VPS (copy SSH):</strong></p>"
        f"<pre style=\"background:#f4f4f5;padding:12px;border-radius:8px;"
        f"font-size:13px;line-height:1.45;white-space:pre-wrap\">"
        f"{html.escape(recovery_cmds)}</pre>"
    )

    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
            logger.info("ops_health_alert sent kind=%s to=%s", alert_kind, addr)
        except Exception:
            logger.exception("ops_health_alert failed kind=%s to=%s", alert_kind, addr)


def notify_ops_health_alert(
    alert_kind: str,
    title: str,
    *,
    detail: str = "",
    pool_snap: Optional[dict] = None,
    heavy_hints: Optional[Iterable[str]] = None,
    action: str = "",
    env_recipients_only: bool = False,
    force: bool = False,
) -> None:
    """
    Gửi email admin (async thread) nếu qua cooldown.
    alert_kind: pool_exhaustion | pool_restart | storefront_down | ...
    """
    if not _alert_enabled():
        return

    kind = (alert_kind or "ops").strip().lower()
    now = time.time()
    if not force and now - _last_sent.get(kind, 0.0) < _cooldown_seconds():
        return
    _last_sent[kind] = now
    _prune_cooldown_cache()

    threading.Thread(
        target=_send_ops_alert_email_task,
        kwargs={
            "alert_kind": kind,
            "title": title,
            "detail": detail or title,
            "pool_snap": pool_snap,
            "heavy_hints": heavy_hints,
            "action": action,
            "env_recipients_only": env_recipients_only,
        },
        daemon=True,
        name=f"ops-alert-{kind}",
    ).start()
