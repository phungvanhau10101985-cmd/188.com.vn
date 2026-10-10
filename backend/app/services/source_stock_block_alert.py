"""Email admin khi Vipomall, PandaMall và CSSBuy cùng bị Cloudflare/CAPTCHA."""
from __future__ import annotations

import html
import logging
import threading
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last_sent_mono = 0.0
_COOLDOWN_SECONDS = 30 * 60


def maybe_notify_admin_all_platforms_blocked(
    *,
    product_id: Optional[int] = None,
    product_name: str = "",
    link: str = "",
    detail: str = "",
) -> bool:
    """
    Gửi email admin. Trả True nếu đã gửi.
    Cùng một đợt chặn chỉ gửi một lần mỗi 30 phút để không spam khi nhiều SP dính Cloudflare.
    """
    global _last_sent_mono
    now_m = time.monotonic()
    with _lock:
        if _last_sent_mono and (now_m - _last_sent_mono) < _COOLDOWN_SECONDS:
            logger.info("source stock block alert: cooldown, bỏ qua email admin")
            return False
        _last_sent_mono = now_m

    thread = threading.Thread(
        target=_send,
        kwargs={
            "product_id": product_id,
            "product_name": product_name,
            "link": link,
            "detail": detail,
        },
        name="source-stock-block-alert",
        daemon=True,
    )
    thread.start()
    return True


def _send(*, product_id: Optional[int], product_name: str, link: str, detail: str) -> None:
    if not settings.is_smtp_configured():
        logger.warning("source stock block alert: SMTP chưa cấu hình, không gửi email admin")
        return
    try:
        from app.services.auth_failure_alert import _get_admin_recipient_emails
        from app.services.email_service import send_email
    except Exception:
        logger.exception("source stock block alert: không import được email")
        return

    recipients = _get_admin_recipient_emails()
    if not recipients:
        logger.warning("source stock block alert: không có email admin")
        return

    subject = "[188] Kiểm tra tồn nguồn: cả 3 nền bị Cloudflare"
    if getattr(settings, "EMAIL_SUBJECT_PREFIX", ""):
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"
    name = (product_name or "").strip() or "—"
    url = (link or "").strip() or "—"
    pid = str(product_id) if product_id else "—"
    err = (detail or "").strip() or "—"
    text_body = "\n".join(
        [
            "Vipomall, PandaMall và CSSBuy đều bị Cloudflare/CAPTCHA.",
            "Worker kiểm tra tồn nguồn đã dừng, không chạy sản phẩm tiếp theo và không gắn cờ hết hàng.",
            "Bật lại trong Quản trị → Kiểm tra nguồn hàng sau khi Cloudflare hết chặn.",
            "",
            f"Sản phẩm: {name}",
            f"ID: {pid}",
            f"Link: {url}",
            "",
            err,
            "",
            "Vào Quản trị → Kiểm tra nguồn hàng để xem. Email này gửi tối đa một lần mỗi 30 phút.",
        ]
    )
    html_body = (
        "<p><strong>Vipomall, PandaMall và CSSBuy đều bị Cloudflare/CAPTCHA.</strong></p>"
        "<p>Worker kiểm tra tồn nguồn <strong>đã dừng</strong>, không chạy sản phẩm tiếp theo và không gắn cờ hết hàng. "
        "Bật lại trong <b>Quản trị → Kiểm tra nguồn hàng</b> sau khi Cloudflare hết chặn.</p>"
        f"<p><strong>Sản phẩm:</strong> {html.escape(name)}<br>"
        f"<strong>ID:</strong> {html.escape(pid)}<br>"
        f"<strong>Link:</strong> {html.escape(url)}</p>"
        f"<pre style=\"white-space:pre-wrap\">{html.escape(err[:2000])}</pre>"
        "<p>Vào <b>Quản trị → Kiểm tra nguồn hàng</b>. Email này gửi tối đa một lần mỗi 30 phút.</p>"
    )
    for addr in recipients:
        try:
            send_email(addr, subject, text_body, html_body)
            logger.info("source stock block alert sent to=%s product_id=%s", addr, pid)
        except Exception:
            logger.exception("source stock block alert failed to=%s", addr)
