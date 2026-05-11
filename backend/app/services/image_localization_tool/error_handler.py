# error_handler.py
import time
from typing import Any, Callable, Tuple


def _max_slow_waits_from_config() -> int:
    try:
        import config as cfg

        raw = getattr(cfg, "OCR_SMART_RETRY_MAX_SLOW_WAITS", 0)
        return max(0, int(raw))
    except Exception:
        return 0


class ErrorHandler:
    """
    Retry OCR / mạng: mặc định chờ và thử lại lâu dài.
    Chi tiết OCR Google Vision được coi là "fatal" nếu thiếu key / không bật API — tránh chờ treo không kết thúc.
    Override số vòng chờ tối đa: OCR_SMART_RETRY_MAX_SLOW_WAITS (inject từ FastAPI qua IMAGE_LOCALIZATION_OCR_MAX_SLOW_WAITS).
    """

    def __init__(self):
        self.fatal_errors = {
            "insufficient_balance": ["insufficient", "balance", "payment required", "402"],
            "invalid_api_key": ["invalid api key", "unauthorized", "401", "authentication failed"],
            "account_suspended": ["suspended", "terminated", "disabled"],
            "quota_exceeded": ["quota exceeded", "rate limit exceeded"],
            # Thiếu/sai GCP JSON trên VPS
            "gcp_credentials_or_file": [
                "could not deserialize",
                "could not deserialize key",
                "no such file or directory",
                "cannot find the file specified",
                "errno 2",
                "errno 13",
                "filenotfounderror",
                "is not valid json",
                "private key must be valid",
                "invalid_grant",
                "invalid json",
                "permission denied:",
                "failed to deserialize",
                "credentials are invalid",
                "could not locate credentials",
                "default credentials were not found",
                "credentials file",
            ],
            "vision_api_not_ready": [
                "cloud vision api has not been used",
                "access not configured",
                "api has been disabled",
                "billing_disabled",
                "billing not enabled",
                "SERVICE_DISABLED",
            ],
        }
        self.error_stats = {}

    def is_fatal_error(self, error_msg: str) -> Tuple[bool, str]:
        error_lower = (error_msg or "").lower()
        for error_type, keywords in self.fatal_errors.items():
            for kw in keywords:
                if kw.lower() in error_lower:
                    return True, error_type
        return False, ""

    def smart_retry(self, func: Callable, *args, max_immediate_retries: int = 3, long_wait_minutes: int = 3, **kwargs) -> Any:
        immediate_retry_count = 0
        slow_rounds_completed = 0
        max_slow = _max_slow_waits_from_config()

        while True:
            try:
                return func(*args, **kwargs)

            except Exception as e:
                error_msg = str(e)

                try:
                    for sub in getattr(e, "args", ()):
                        if isinstance(sub, str) and len(sub) > len(error_msg):
                            error_msg += " " + sub
                except Exception:
                    pass

                is_fatal, error_type = self.is_fatal_error(error_msg)
                if is_fatal:
                    print(f"\n❌ LỖI FATAL ({error_type}): {error_msg}")
                    print("🚫 Chương trình buộc phải DỪNG LẠI.")
                    raise e

                if immediate_retry_count < max_immediate_retries:
                    immediate_retry_count += 1
                    print(f"  ⚠️ Lỗi tạm thời: {error_msg}")
                    print(f"  🔄 Thử lại ngay ({immediate_retry_count}/{max_immediate_retries}) sau 5s...")
                    time.sleep(5)
                    continue

                if max_slow and slow_rounds_completed >= max_slow:
                    raise TimeoutError(
                        f"OCR/Google Vision chờ đủ {max_slow} vòng ({long_wait_minutes} phút/vòng sau retry nhanh): {error_msg}. "
                        "Trên VPS: kiểm tra IMAGE_LOCALIZATION_GCP_KEY_FILE, bật Cloud Vision API, billing GCP, egress HTTPS; "
                        "hoặc tăng IMAGE_LOCALIZATION_OCR_MAX_SLOW_WAITS (đặt 0 trong .env = không giới hạn — như cũ)."
                    ) from e

                slow_rounds_completed += 1
                print(f"  ⚠️ Vẫn lỗi sau {max_immediate_retries} lần thử nhanh: {error_msg}")
                print(f"  ⏳ ĐANG CHỜ {long_wait_minutes} PHÚT để mạng/server hồi phục...")
                if max_slow:
                    print(
                        f"  (OCR chờ ẩn đến slow round {slow_rounds_completed}/{max_slow}; xong {max_slow} vòng vẫn lỗi sẽ dừng)"
                    )
                else:
                    print(
                        "  (Mặc định không giới hạn vòng chờ OCR — có thể chờ treo nếu thiếu key/Vision; "
                        "đặt IMAGE_LOCALIZATION_OCR_MAX_SLOW_WAITS trên server.)"
                    )

                time.sleep(long_wait_minutes * 60)

                immediate_retry_count = 0
                print("  🔄 Hết thời gian chờ, đang thử lại kết nối...")

    def log_error(self, service: str, error_type: str):
        if service not in self.error_stats:
            self.error_stats[service] = {}
        if error_type not in self.error_stats[service]:
            self.error_stats[service][error_type] = 0
        self.error_stats[service][error_type] += 1

    def get_stats(self):
        return self.error_stats
