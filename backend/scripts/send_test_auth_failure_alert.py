"""
Mô phỏng lỗi đăng nhập khách → gửi email cảnh báo tới mọi admin_users đang bật.

Chạy từ thư mục backend:
  python scripts/send_test_auth_failure_alert.py
  python scripts/send_test_auth_failure_alert.py --dry-run   # chỉ in nội dung, không gửi SMTP
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from app.core.config import settings  # noqa: E402
from app.services.auth_failure_alert import (  # noqa: E402
    _get_admin_recipient_emails,
    _send_auth_failure_emails_task,
)


def _preview_email() -> tuple[str, str]:
    """Trả về (subject, text_body) giống mail thật."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    path = "/api/v1/auth/email/request"
    method = "POST"
    status_code = 500
    detail = "Không gửi được email. Thử lại sau."
    customer_email = "khach.thu@example.com"
    client_ip = "203.0.113.42"

    subject = "[188] Sự cố đăng nhập khách"
    if settings.EMAIL_SUBJECT_PREFIX:
        subject = f"{settings.EMAIL_SUBJECT_PREFIX} {subject}"

    email_line = customer_email
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
    return subject, text_body


def main() -> None:
    parser = argparse.ArgumentParser(description="Test email cảnh báo lỗi đăng nhập khách")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ in subject/body và danh sách người nhận, không gửi SMTP",
    )
    args = parser.parse_args()

    recipients = _get_admin_recipient_emails()
    subject, text_body = _preview_email()

    print("=" * 60)
    print("TEST — Cảnh báo lỗi đăng nhập khách (mô phỏng)")
    print("=" * 60)
    print(f"AUTH_LOGIN_FAILURE_ALERT_ENABLED: {settings.AUTH_LOGIN_FAILURE_ALERT_ENABLED}")
    print(f"SMTP configured: {settings.is_smtp_configured()}")
    print(f"Số admin nhận mail: {len(recipients)}")
    if recipients:
        for e in recipients:
            print(f"  → {e}")
    else:
        print("  (không có admin_users.is_active + email hợp lệ)")
    print()
    print(f"Subject: {subject}")
    print("-" * 60)
    print(text_body)
    print("-" * 60)

    if args.dry_run:
        print("\n[dry-run] Không gửi SMTP.")
        return

    if not settings.is_smtp_configured():
        print("\nLỗi: SMTP chưa cấu hình — không gửi được.", file=sys.stderr)
        sys.exit(2)
    if not recipients:
        print("\nLỗi: Không có email admin để gửi.", file=sys.stderr)
        sys.exit(3)

    _send_auth_failure_emails_task(
        path="/api/v1/auth/email/request",
        method="POST",
        status_code=500,
        detail="Không gửi được email. Thử lại sau.",
        customer_email="khach.thu@example.com",
        client_ip="203.0.113.42",
    )
    print(f"\nĐã gửi (hoặc cố gửi) tới {len(recipients)} địa chỉ admin. Kiểm tra hộp thư (và thư rác).")


if __name__ == "__main__":
    main()
