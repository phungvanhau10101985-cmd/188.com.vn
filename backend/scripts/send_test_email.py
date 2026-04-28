"""
Gửi một email thử (cần .env giống production).
Chạy từ thư mục backend:
  python scripts/send_test_email.py you@example.com
"""
import os
import sys
from pathlib import Path

# backend/ là cwd mong muốn
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

from app.core.config import settings  # noqa: E402
from app.services.email_service import send_email  # noqa: E402


def main() -> None:
    to = (sys.argv[1] or "").strip() if len(sys.argv) > 1 else (settings.TEST_EMAIL or "").strip()
    if not to:
        print("Dùng: python scripts/send_test_email.py nguoidung@email.com", file=sys.stderr)
        print("hoặc đặt TEST_EMAIL trong .env", file=sys.stderr)
        sys.exit(1)
    if not settings.is_smtp_configured():
        print(
            "is_smtp_configured() = False. Cần: SMTP_HOST, SMTP_USER, SMTP_PASS, "
            "và SMTP_FROM hoặc SENDER_EMAIL/EMAIL_FROM.",
            file=sys.stderr,
        )
        sys.exit(2)
    send_email(
        to,
        "Test gửi mail — 188.com.vn",
        "Đây là email thử từ backend (python scripts/send_test_email.py).",
    )
    print("Đã gửi tới", to)


if __name__ == "__main__":
    main()
