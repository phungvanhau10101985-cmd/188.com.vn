"""Gửi email marketing tới danh sách newsletter (nền)."""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings
from app.crud import newsletter as crud_newsletter
from app.db.session import SessionLocal
from app.services.email_service import send_marketing_email
from app.services.email_warmup import can_send_today, record_send

logger = logging.getLogger(__name__)

_SEND_LOCK = threading.Lock()
_LAST_JOB: dict | None = None


def get_last_campaign_job() -> dict | None:
    with _SEND_LOCK:
        return dict(_LAST_JOB) if _LAST_JOB else None


def run_newsletter_campaign_task(*, subject: str, message: str) -> None:
    db = SessionLocal()
    sent = 0
    failed = 0
    deferred_quota = 0
    try:
        if not settings.is_smtp_configured():
            logger.warning("newsletter campaign skip: SMTP not configured")
            return
        for email in crud_newsletter.iter_active_subscriber_emails(db):
            if not can_send_today(db):
                deferred_quota += 1
                logger.info(
                    "newsletter campaign stopped: daily warm-up quota reached (deferred=%s)",
                    deferred_quota,
                )
                break
            try:
                send_marketing_email(email, subject=subject, message=message)
                record_send(db, channel="marketing")
                sent += 1
            except Exception as exc:
                failed += 1
                logger.warning("newsletter campaign fail email=%s: %s", email, exc)
            time.sleep(0.05)
        logger.info(
            "newsletter campaign done sent=%s failed=%s deferred_quota=%s",
            sent,
            failed,
            deferred_quota,
        )
    finally:
        db.close()
        with _SEND_LOCK:
            global _LAST_JOB
            _LAST_JOB = {
                "status": "done",
                "sent": sent,
                "failed": failed,
                "deferred_quota": deferred_quota,
                "subject": subject,
            }


def queue_newsletter_campaign(*, subject: str, message: str) -> None:
    with _SEND_LOCK:
        global _LAST_JOB
        _LAST_JOB = {"status": "running", "sent": 0, "failed": 0, "subject": subject}
    thread = threading.Thread(
        target=run_newsletter_campaign_task,
        kwargs={"subject": subject, "message": message},
        daemon=True,
    )
    thread.start()
