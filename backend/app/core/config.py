# backend/app/core/config.py - COMPLETE VERSION (ĐÃ FIX DATABASE PATH)
import os
import re
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from dotenv import load_dotenv
from pathlib import Path

# Load .env từ thư mục backend (luôn đúng dù chạy uvicorn từ repo root hay từ backend/)
_backend_root = Path(__file__).resolve().parents[2]
load_dotenv(_backend_root / ".env")
load_dotenv(_backend_root / ".env.local", override=True)  # ghi đè .env (dev/local, không commit)
load_dotenv(override=False)  # cwd .env — chỉ bổ sung biến chưa có (không đè .env.local)


def _normalize_gemini_model(raw: Optional[str]) -> Tuple[str, bool]:
    """
    Chuẩn hoá model Gemini trong Settings.
    gemini-2.0-flash* trong .env cũ → gemini-2.5-flash (Google deprecates / hay lỗi 429).
    Trả về (model, đã đổi so với chuỗi đầu vào không rỗng).
    """
    n = (raw or "").strip()
    if not n:
        return ("gemini-2.5-flash", False)
    low = n.lower()
    if re.match(r"^gemini-2\.0-flash", low):
        return ("gemini-2.5-flash", True)
    return (n, False)


_settings_logger = logging.getLogger(__name__)


class Settings:
    def __init__(self):
        # ========================
        # PROJECT CONFIGURATION
        # ========================
        self.PROJECT_NAME: str = os.getenv("PROJECT_NAME", "188-com-vn")
        self.API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")
        self.SERVER_NAME: str = os.getenv("SERVER_NAME", "188.com.vn")
        self.SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
        self.SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8001"))
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # development/staging/production
        self.DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
        
        # ========================
        # DATABASE CONFIGURATION - PostgreSQL / SQLite
        # ========================
        current_dir = Path(__file__).parent.parent.parent  # backend/app/core -> backend
        env_url = os.getenv("DATABASE_URL", "").strip()
        
        if env_url and ("postgresql://" in env_url or "postgres://" in env_url):
            # PostgreSQL: dùng DATABASE_URL từ .env
            self.DATABASE_URL = env_url.replace("postgres://", "postgresql://", 1)  # postgres:// -> postgresql://
            self.ACTUAL_DATABASE_PATH = None  # Không áp dụng cho PostgreSQL
            self.IS_POSTGRESQL = True
        elif env_url and "sqlite" in env_url:
            # SQLite từ .env
            if "./" in env_url or "app.db" in env_url:
                rest = env_url.replace("sqlite:///", "").strip().lstrip("./")
                abs_path = (current_dir / rest).resolve().as_posix()
                self.DATABASE_URL = f"sqlite:///{abs_path}"
                self.ACTUAL_DATABASE_PATH = Path(abs_path)
            else:
                self.DATABASE_URL = env_url
                self.ACTUAL_DATABASE_PATH = Path(env_url.replace("sqlite:///", ""))
            self.IS_POSTGRESQL = False
        else:
            # Fallback: SQLite local (development)
            actual_db_path = current_dir / "app.db"
            self.DATABASE_URL = f"sqlite:///{actual_db_path.resolve().as_posix()}"
            self.ACTUAL_DATABASE_PATH = actual_db_path
            self.IS_POSTGRESQL = False
        
        # PostgreSQL: QueuePool — pool nhỏ + nhiều request đồng thời → TimeoutError (sqlalchemy.me/e/20/3o7r)
        self.DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "15"))
        self.DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "25"))
        self.DATABASE_POOL_RECYCLE: int = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))
        self.DATABASE_POOL_TIMEOUT: int = int(os.getenv("DATABASE_POOL_TIMEOUT", "60"))
        
        # Cây danh mục /menu (GET /categories/from-products): chỉ giữ nhánh có số SP active **lớn hơn** ngưỡng này.
        # 0 = hành vi cũ (ẩn nhánh 0 SP). Mặc định 10 → hiển thị khi có ≥11 SP; ≤10 SP thì ẩn khỏi menu/sitemap dùng cây này.
        self.CATEGORY_MENU_MIN_PRODUCT_COUNT: int = int(os.getenv("CATEGORY_MENU_MIN_PRODUCT_COUNT", "10"))
        
        # ========================
        # SECURITY CONFIGURATION
        # ========================
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "H8$kL3!pQ7@mR2#sV5%wZ9^yB1*nJ4(cF6_gH0)dA+eQ~lO{iU[Y}8P]3rT|5W")
        self.ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))  # 7 days
        # Phiên sau đăng nhập OTP email (JWT) — mặc định 365 ngày, coi như "giữ đăng nhập" lâu trên từng trình duyệt
        self.EMAIL_OTP_REMEMBER_DAYS: int = int(os.getenv("EMAIL_OTP_REMEMBER_DAYS", "365"))
        # Cookie httpOnly cho JWT (luồng /auth/email/*)
        self.AUTH_JWT_COOKIE_NAME: str = os.getenv("AUTH_JWT_COOKIE_NAME", "188_access_token").strip() or "188_access_token"
        _env = os.getenv("ENVIRONMENT", "development").lower()
        _cookie_secure_env = os.getenv("AUTH_COOKIE_SECURE", "").strip().lower()
        self.AUTH_COOKIE_SECURE: bool = (
            _cookie_secure_env in ("1", "true", "yes") or _env == "production"
        )
        _ss = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
        self.AUTH_COOKIE_SAMESITE: str = _ss if _ss in ("lax", "strict", "none") else "lax"
        self.FRONTEND_BASE_URL: str = (os.getenv("FRONTEND_BASE_URL", "http://localhost:3001").strip().rstrip("/") or "http://localhost:3001")
        self.BACKEND_PUBLIC_URL: str = (
            os.getenv("BACKEND_PUBLIC_URL", "").strip().rstrip("/")
            or f"http://{os.getenv('SERVER_HOST', '127.0.0.1')}:{os.getenv('SERVER_PORT', '8001')}".replace("0.0.0.0", "127.0.0.1")
        )
        # Meta Conversion API — bí mật gọi POST /embed-codes/facebook/capi/send-event (Authorization: Bearer …)
        self.FACEBOOK_GRAPH_API_VERSION: str = (os.getenv("FACEBOOK_GRAPH_API_VERSION", "v21.0").strip() or "v21.0").lstrip("/")
        self.FACEBOOK_CAPI_INGEST_SECRET: str = os.getenv("FACEBOOK_CAPI_INGEST_SECRET", "").strip()

        # Bunny.net — Storage Zone API + Pull Zone (ảnh). Frontend: NEXT_PUBLIC_CDN_URL nên trùng BUNNY_CDN_PUBLIC_BASE.
        self.BUNNY_STORAGE_ZONE_NAME: str = os.getenv("BUNNY_STORAGE_ZONE_NAME", "").strip()
        self.BUNNY_STORAGE_ACCESS_KEY: str = os.getenv("BUNNY_STORAGE_ACCESS_KEY", "").strip()
        self.BUNNY_CDN_PUBLIC_BASE: str = (
            os.getenv("BUNNY_CDN_PUBLIC_BASE", "").strip().rstrip("/")
            or "https://188comvn.b-cdn.net"
        )
        self.BUNNY_UPLOAD_PATH_PREFIX: str = (
            os.getenv("BUNNY_UPLOAD_PATH_PREFIX", "site").strip().strip("/") or "site"
        )
        self.BUNNY_WEB_PUBLIC_PREFIX: str = os.getenv("BUNNY_WEB_PUBLIC_PREFIX", "").strip().strip("/")

        # Feed TSV Google Merchant Center — GET /api/v1/import-export/export/merchant-center-feed.tsv (công khai)
        self.MERCHANT_FEED_CURRENCY: str = os.getenv("MERCHANT_FEED_CURRENCY", "VND").strip() or "VND"
        _merch_feed_img_base = os.getenv("MERCHANT_FEED_IMAGE_BASE_URL", "").strip().rstrip("/")
        self.MERCHANT_FEED_IMAGE_BASE_URL: str = _merch_feed_img_base or self.BUNNY_CDN_PUBLIC_BASE
        # Feed Meta catalogue (fb_product_category phải thuộc taxonomy Meta — đổi theo ngành hàng thật)
        self.META_FEED_FB_PRODUCT_CATEGORY: str = (
            os.getenv("META_FEED_FB_PRODUCT_CATEGORY", "").strip()
            or "Apparel & Accessories"
        )
        # Dùng chung làm fallback google_product_category nếu không map từng SKU (trống = dùng breadcrumb category trong DB)
        self.CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY: str = (
            os.getenv("CATALOG_FEED_DEFAULT_GOOGLE_PRODUCT_CATEGORY", "").strip()
        )

        self.EMAIL_TRUSTED_DEVICE_DAYS: int = int(os.getenv("EMAIL_TRUSTED_DEVICE_DAYS", "30"))
        self.EMAIL_AUTH_RL_EMAIL_PER_MINUTE: int = int(os.getenv("EMAIL_AUTH_RL_EMAIL_PER_MINUTE", "5"))
        self.EMAIL_AUTH_RL_IP_PER_MINUTE: int = int(os.getenv("EMAIL_AUTH_RL_IP_PER_MINUTE", "40"))
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
        self.PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_HOURS", "24"))
        # Web Push (PWA) — tạo: npx web-push generate-vapid-keys
        self.VAPID_PUBLIC_KEY: str = os.getenv("VAPID_PUBLIC_KEY", "").strip()
        self.VAPID_PRIVATE_KEY: str = os.getenv("VAPID_PRIVATE_KEY", "").strip().replace("\\n", "\n")
        self.VAPID_CLAIM_EMAIL: str = os.getenv("VAPID_CLAIM_EMAIL", "mailto:noreply@188.com.vn").strip()

        # ========================
        # OTP CONFIGURATION
        # ========================
        self.OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))
        self.OTP_LENGTH: int = int(os.getenv("OTP_LENGTH", "6"))
        self.OTP_MAX_RETRIES: int = int(os.getenv("OTP_MAX_RETRIES", "3"))
        self.OTP_RESEND_DELAY_SECONDS: int = int(os.getenv("OTP_RESEND_DELAY_SECONDS", "60"))
        self.OTP_DAILY_LIMIT: int = int(os.getenv("OTP_DAILY_LIMIT", "5"))
        
        # OTP Provider Priority (firebase, zalo, console)
        self.OTP_PRIMARY_PROVIDER: str = os.getenv("OTP_PRIMARY_PROVIDER", "firebase")
        self.OTP_FALLBACK_ENABLED: bool = os.getenv("OTP_FALLBACK_ENABLED", "True").lower() == "true"
        self.OTP_SIMULATION_MODE: bool = os.getenv("OTP_SIMULATION_MODE", "False").lower() == "true"
        
        # ========================
        # ZALO OTP CONFIGURATION
        # ========================
        self.ZALO_OA_ID: str = os.getenv("ZALO_OA_ID", "1714121106420519241")
        self.ZALO_OA_SECRET: str = os.getenv("ZALO_OA_SECRET", "2689291499106432813")
        self.ZALO_OA_ACCESS_TOKEN: str = os.getenv("ZALO_OA_ACCESS_TOKEN", "QxshTQU4E1TYiA1rfu0t6c2ohd2dd4H3DCQgSeYMVnW9kwOCpCjG9cADnahRx3z-Uhkl2DhzFW96jDayWlSKAo6emHgUu1OC2P256RF_Uo0LjkD3qDDpRNQBbcAsmrDDEA-OUfl_I1SYjAKXhlbqDtUGdrJglGnvRiISIFktLMTV_fnftSqGQ4QkuL75o1b-GVpmQksq5rH0__jCsSS2NNM4obFpr1ncRBoASQxFMnm5lSCOdF0nAZxTf3whi7nK38YfG9dXV6zUZPHGnjbVOMIsgnUZpZeA8At3ExcR4Wmupi4IWO4tU4Fezq_Rhtj5HUkG9i6cN1XWpimot9SNNd6kt6_TsaL77-cZQjYkOrzev_LlzQOiTshIj5pLXtzrIVIgLjZ4GLfbWhPjekeXKc6_kLz7UVG0eLkhapWO")
        self.ZALO_REFRESH_TOKEN: str = os.getenv("ZALO_REFRESH_TOKEN", "QiziOEF2O11ZgcTWuyPl7M70QMNZscDL3RmqJ_d9Q30YeZK_oi5fJn321aphlcTQ4_uhPCEXM6b4-1PlZOjU5WNR1ZVSWq16GDHCF9RP1YfBg1K5hiLZ2c_SC7hfgMS2EkSs7jISQoy6_s09WQCo0tBZP0ccfMigSDKo5eEjUsbGhZDXrgnfV3NtOrRta0ftTTPRHl20Btbtx7CTeO8QOIJFI5BYpmHp8BDqIkR-9qmxYKD_vybDTHYH0stEbs9G1lOvIUsAOqKTxGb7tB53NoZd1MFtkNDT7BuKLjdFJciUoIzsxALYVJcbD5VdfcyfU_ydAxcCImX7tpmKgQSsDLlKUII4XIGLOl102wkCE0L-o6WRh8i79Ipr3LMgy0TETP5qJfRrV652e2r-mUrQSB4qFadlrM0V")
        self.ZALO_API_BASE_URL: str = os.getenv("ZALO_API_BASE_URL", "https://openapi.zalo.me/v3.0/oa")
        
        # Zalo Template IDs for different purposes
        self.ZALO_TEMPLATE_REGISTER: str = os.getenv("ZALO_TEMPLATE_REGISTER", "304254")
        self.ZALO_TEMPLATE_RESET_PASSWORD: str = os.getenv("ZALO_TEMPLATE_RESET_PASSWORD", "304255")
        self.ZALO_TEMPLATE_VERIFY_PHONE: str = os.getenv("ZALO_TEMPLATE_VERIFY_PHONE", "304256")
        self.ZALO_TEMPLATE_LOGIN: str = os.getenv("ZALO_TEMPLATE_LOGIN", "304257")
        
        # ========================
        # FIREBASE CONFIGURATION - FIXED WITH TOKEN_URI
        # ========================
        self.FIREBASE_PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "comvn-320603")
        self.FIREBASE_PRIVATE_KEY: str = os.getenv("FIREBASE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQCootFfgyYq1gl5\nD9nYZ4baYmqhntyJoENN5UUia7Kc7QQlPwdryki0XewOSdk12tBQnU+udQDs2D3m\n9VMUo3F+6rTylQx0tFKmweeeIgCd0CoX8GjPKxOqINnqDvMYRDJe1QvXNU1HyJiB\nwNYuto7nAH0vDIL0lcTPhoysPUeY37JIl8jWa0Ee6+dTIdDGoBGtBjue2u7+HXYG\nVd3hoW+niAv5il1ZloJTqpfg2NZLrHwKtAgMc6BWxh8FDylH5YRG8sRYRRD6i1hH\nZONcaR7I4Gx7+g2tpxFp8c02dnGl0nPdkkrrCzEeu8Qaw66bSgFUE+zK5EQZRE40\nw6OM8rYlAgMBAAECggEAAcxyxT0F3DEaOsNThH5eLtgb4QtruMAP17XZTeuuJQRW\nJfuNHbYznlDeIqzg9zUVQbbb0bWHw/7uchctwquXm03vjiLO1jPSKdspmEMulIBS\n4px60bLY69ib2mY8a4bWrrJBBROZdmmKTt/6qNbjoU0dCLJudyNdzQTXXULuD5BW\nw1eIReWa9zF2hrKe/kmMcCIEd7MqLQcB+UHJdc9i+cs/LRmT/ujbPEfEloMwP8w9\nnO8KU0KQckuj/HXzXkcm605rP+3j2E35yWRmt7/wodFeu1cqC90N/6B2dpKEmBle\nG3xj6JjNbWz3ez+GajZFI+gyX/XSgOlAaC1LqPD+hQKBgQDsZ07N013Hen6Ems/r\nMfqWBfGxvEjbyeHqk14y1eKds+w+F1K0kCNs0GNo1c7nWEeJb6R+l04R64ZWA1KN\nVH5wFOCYT8Uf8Uyfypaz2Ha55lvtw0Tk2WC2cFnqwKTK+UwI1ZGvacxuUdglrogq\n/gpxAZLV37swWRYrunTp5kZGPwKBgQC2nWxHw7z0ChWXZjqSHLA0Wl6qN6wflfNl\nQ3G6k08yNLemM/p2bwsE+2cYO9SMzdvTC59fmLZT31CHacV2JQU4psbjwcPHNrlg\ndK3qm4LrBDXrO9vWyCbo01XtzP2J4aS9fQQgFmjejQT7AI5oPiRVSw5anXInoAp+\nPxYEpJpSmwKBgQDrslBqfCtK4EFV+ngEWc8qVoDUIRJPOC.frVcScUI1hiGqouV43\nMmJvchE7C7j/BRBF4a6SnE41JarJBQUAbdal7trCYP37y/wGcNjyNIai8B6FnqOI\nu4ZmPvwXRrzGteluAWkACC7PawBjCXEv1Bsa8mOwoyEhoiCttngsX+9+xwKBgQCh\nMhC0wGl4mbY5cHnfJAe+Ds9lPcNoFjtFdeVcJlBQJwy9X0CFbruxaCG22IlkyQp0\nHtxNzEWVf5hcD9fH1CHpwf3qac3hecLlC9nBMAi+X3cg8DO8Qe1ms7Y0NTDQlyeO\nRF5x3JYxbRWqYvFRvxjfWWOQRU7Q/4qDqjhLXOkEZQKBgQDF3jDzyRm+99rUZsNg\nxbgkTy5Pzde/5UDaO9gEyr9Poifm7VCuLe5FhTgi1WHGuSkDxk4+Y9B4hRQf871w\nlwuFY08T5WPR/hEZrF6Z8d6ch+RVmU0sZo1XBytPb0VXcw/ZbFuR6AnCXf48per9\n2Rn/M/Ay/aZT9WHKXkoF+nF8tA==\n-----END PRIVATE KEY-----").replace('\\n', '\n')
        self.FIREBASE_CLIENT_EMAIL: str = os.getenv("FIREBASE_CLIENT_EMAIL", "firebase-adminsdk-t34so@comvn-320603.iam.gserviceaccount.com")
        self.FIREBASE_TOKEN_URI: str = os.getenv("FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token")
        self.FIREBASE_DATABASE_URL: str = os.getenv("FIREBASE_DATABASE_URL", "https://comvn-320603.firebaseio.com")
        
        # Firebase Web App Config (for frontend)
        self.FIREBASE_API_KEY: str = os.getenv("FIREBASE_API_KEY", "AIzaSyCoyAphRSlXKvMr7ZkCnXn15GFaz14sJb4")
        self.FIREBASE_AUTH_DOMAIN: str = os.getenv("FIREBASE_AUTH_DOMAIN", "comvn-320603.firebaseapp.com")
        self.FIREBASE_STORAGE_BUCKET: str = os.getenv("FIREBASE_STORAGE_BUCKET", "comvn-320603.firebasestorage.app")
        self.FIREBASE_MESSAGING_SENDER_ID: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "746017912204")
        self.FIREBASE_APP_ID: str = os.getenv("FIREBASE_APP_ID", "1:746017912204:web:93f5196ffd202205b692a9")
        # Fallback OTP: URL webhook (Cloud Function) nhận POST { "phone", "otp" }. Để trống = log OTP ra console.
        self.FIREBASE_OTP_WEBHOOK_URL: str = os.getenv("FIREBASE_OTP_WEBHOOK_URL", "")
        
        # ========================
        # AI APIs CONFIGURATION
        # ========================
        self.DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_API_URL: str = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
        self.DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        # Đổi tên từ DEEPSEEK_SEARCH_CORRECTION_ENABLED -> AI_SEARCH_CORRECTION_ENABLED cho đúng bản chất (dùng Gemini)
        # Vẫn giữ fallback đọc biến cũ để tương thích ngược
        self.AI_SEARCH_CORRECTION_ENABLED: bool = (
            os.getenv("AI_SEARCH_CORRECTION_ENABLED", "True").lower() == "true" or 
            os.getenv("DEEPSEEK_SEARCH_CORRECTION_ENABLED", "True").lower() == "true"
        )
        self.DEEPSEEK_SEARCH_CORRECTION_ENABLED = self.AI_SEARCH_CORRECTION_ENABLED  # Alias cho code cũ

        # Gemini - dùng cho SEO danh mục, sửa từ khóa, phân loại sản phẩm
        # Model mặc định: gemini-2.5-flash (2.0-flash trong .env được chuẩn hoá tự động).
        # Tham khảo khác: gemini-2.5-pro (chậm, đắt hơn), gemini-2.5-flash-lite (rẻ, ngữ cảnh ngắn).
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        _gemini_raw = os.getenv("GEMINI_MODEL")
        _gemini_norm, _gemini_replaced = _normalize_gemini_model(_gemini_raw or "gemini-2.5-flash")
        self.GEMINI_MODEL: str = _gemini_norm
        if _gemini_replaced and (_gemini_raw or "").strip():
            _settings_logger.warning(
                "GEMINI_MODEL=%s đã được chuẩn hoá thành %s — cập nhật backend/.env để tránh cảnh báo.",
                (_gemini_raw or "").strip(),
                self.GEMINI_MODEL,
            )

        # Category SEO: tự động duyệt mapping khi AI confidence đủ cao
        self.CATEGORY_SEO_AUTO_APPROVE: bool = os.getenv("CATEGORY_SEO_AUTO_APPROVE", "True").lower() == "true"
        self.CATEGORY_SEO_AUTO_APPROVE_MIN_CONFIDENCE: float = float(os.getenv("CATEGORY_SEO_AUTO_APPROVE_MIN_CONFIDENCE", "0.85"))
        
        # Không đặt default API key trong code - bắt buộc cấu hình qua .env khi dùng AI
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.OPENAI_API_URL: str = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/chat/completions")
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        
        # ========================
        # SMTP / EMAIL (giống cấu hình Node/nodemailer: isSmtpConfigured = đủ 4 trường)
        # Bắt buộc gửi được: SMTP_HOST, SMTP_USER, SMTP_PASS, và 1 trong (SMTP_FROM | SENDER_EMAIL | EMAIL_FROM)
        # Tương thích tên cũ: SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD
        # ========================
        _smtp_host = (os.getenv("SMTP_HOST", "").strip() or os.getenv("SMTP_SERVER", "").strip())
        self.SMTP_HOST: str = _smtp_host
        self.SMTP_SERVER: str = _smtp_host  # alias

        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        _sec_raw = os.getenv("SMTP_SECURE", "").strip().lower()
        # Giống Node: true/1 => TLS từ đầu, hoặc port 465 mặc định secure
        _env_secure = _sec_raw in ("1", "true", "yes")
        self.SMTP_SECURE: bool = _env_secure or (self.SMTP_PORT == 465)
        # Dùng SMTP_SSL thay vì STARTTLS
        self.SMTP_USE_IMPLICIT_SSL: bool = (self.SMTP_PORT == 465) or _env_secure

        _smtp_user = (os.getenv("SMTP_USER", "").strip() or os.getenv("SMTP_USERNAME", "").strip())
        self.SMTP_USER: str = _smtp_user
        self.SMTP_USERNAME: str = _smtp_user  # alias

        _smtp_pass = (os.getenv("SMTP_PASS", "").strip() or os.getenv("SMTP_PASSWORD", "").strip())
        self.SMTP_PASS: str = _smtp_pass.replace("\\n", "\n")
        self.SMTP_PASSWORD: str = self.SMTP_PASS  # alias

        # Từ gửi: SMTP_FROM dạng "Tên <email@domain.com>" (ưu tiên) hoặc SENDER_EMAIL / EMAIL_FROM
        self.SMTP_FROM: str = os.getenv("SMTP_FROM", "").strip()
        _sender = (os.getenv("SENDER_EMAIL", "").strip() or os.getenv("EMAIL_FROM", "").strip())
        self.SENDER_EMAIL: str = _sender
        self.EMAIL_FROM: str = _sender  # alias (địa chỉ gửi)

        self.SENDER_NAME: str = os.getenv("SENDER_NAME", "").strip()
        self.REPLY_TO: str = os.getenv("REPLY_TO", "").strip()
        self.EMAIL_USE_TLS: bool = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"

        # Tuỳ chọn (template nội dung / test — code có thể đọc sau)
        self.COMPANY_NAME: str = os.getenv("COMPANY_NAME", "").strip()
        self.COMPANY_PHONE: str = os.getenv("COMPANY_PHONE", "").strip()
        self.COMPANY_ADDRESS: str = os.getenv("COMPANY_ADDRESS", "").strip()
        self.WEBSITE_URL: str = os.getenv("WEBSITE_URL", "").strip()
        self.EMAIL_SUBJECT_PREFIX: str = (
            os.getenv("EMAIL_SUBJECT_PREFIX", "").strip() or os.getenv("EMAIL_SUBJECT", "").strip()
        )
        self.TEST_EMAIL: str = os.getenv("TEST_EMAIL", "").strip()
        # Email shop (CSV) nhận thông báo khi khách đã đặt cọc thành công (SePay / admin)
        self.ORDER_DEPOSIT_ALERT_EMAILS: List[str] = [
            x.strip()
            for x in os.getenv("ORDER_DEPOSIT_ALERT_EMAILS", "").split(",")
            if x.strip()
        ]

        # ========================
        # GOOGLE OAUTH CONFIGURATION
        # ========================
        self.GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
        
        # ========================
        # FILE UPLOAD CONFIGURATION
        # ========================
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "app/static/uploads")
        self.MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "10"))
        self.ALLOWED_EXTENSIONS: List[str] = os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,gif,pdf,xlsx,xls").split(",")
        # Import Excel: tối đa số dòng/lần (mặc định 30k); commit DB theo lô để giảm overhead transaction
        self.MAX_EXCEL_IMPORT_ROWS: int = int(os.getenv("MAX_EXCEL_IMPORT_ROWS", "30000"))
        self.EXCEL_IMPORT_COMMIT_BATCH_SIZE: int = int(os.getenv("EXCEL_IMPORT_COMMIT_BATCH_SIZE", "250"))
        # bulk_import_products: sau khi ghi DB có thể chạy Gemini (meta description + seo_body) theo từng path danh mục.
        # Với batch rất lớn (vd. ~30k SP) luồng nền có thể lâu — nếu số dòng import ≥ ngưỡng dưới thì BỎ QUA tự động (chạy script / admin sau).
        # Đặt 0 để luôn cho phép chạy nền khi CATEGORY_GEMINI_SEO_AUTO_ENABLED bật.
        try:
            _seo_skip_thr = os.getenv("EXCEL_IMPORT_AUTO_SKIP_CATEGORY_SEO_MIN_ROWS", "2500").strip()
            self.EXCEL_IMPORT_AUTO_SKIP_CATEGORY_SEO_MIN_ROWS = int(_seo_skip_thr) if _seo_skip_thr != "" else 2500
        except ValueError:
            self.EXCEL_IMPORT_AUTO_SKIP_CATEGORY_SEO_MIN_ROWS = 2500
        # Gemini SEO danh mục tự động (Import Excel + API tạo/sửa SP):
        # CATEGORY_GEMINI_SEO_* trên VPS (staging/production) là điều kiện cần — điều kiện đủ là admin phải bật trong
        # bảng category_seo_settings (PUT /category-seo/app-settings hay trang /admin/danh-muc-seo).
        # Máy dev: luôn tắt (kể cả .env có true — tránh gọi Gemini nhầm).
        _env_for_gemini = (getattr(self, "ENVIRONMENT", "") or "development").strip().lower()
        _gemini_auto_allowed_env = _env_for_gemini in ("production", "staging")
        _cat_auto_raw = os.getenv("CATEGORY_GEMINI_SEO_AUTO_ENABLED", "").strip()
        _legacy_cat_seo_raw = os.getenv("EXCEL_IMPORT_CATEGORY_SEO_BODY_ENABLED", "").strip()
        _want_gemini = (
            _cat_auto_raw.lower() == "true"
            or (_legacy_cat_seo_raw or "false").strip().lower() == "true"
        )
        if _gemini_auto_allowed_env:
            _gemini_cat_auto = _want_gemini
        else:
            _gemini_cat_auto = False
            if _want_gemini:
                _settings_logger.info(
                    "CATEGORY_GEMINI_SEO_AUTO: bỏ qua .env=true — chỉ bật trên VPS (ENVIRONMENT=staging hoặc production). "
                    "Hiện ENVIRONMENT=%s.",
                    getattr(self, "ENVIRONMENT", ""),
                )
        self.CATEGORY_GEMINI_SEO_AUTO_ENABLED: bool = _gemini_cat_auto
        self.EXCEL_IMPORT_CATEGORY_SEO_BODY_ENABLED: bool = _gemini_cat_auto
        # Nếu true: import Excel + API tạo/sửa SP chỉ kích Gemini cho path có trong category_seo_gemini_targets (admin đã đánh dấu).
        self.CATEGORY_GEMINI_SEO_WHITELIST_ONLY: bool = (
            os.getenv("CATEGORY_GEMINI_SEO_WHITELIST_ONLY", "false").strip().lower() == "true"
        )

        # ========================
        # CORS CONFIGURATION
        # ========================
        cors_env = os.getenv(
            "BACKEND_CORS_ORIGINS",
            "http://localhost:3001,http://127.0.0.1:3001",
        )
        self.BACKEND_CORS_ORIGINS: List[str] = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
        # Cho phép tunnel ngrok khi frontend gọi thẳng API (không qua Next proxy). Để trống = tắt.
        _cors_re = os.getenv("BACKEND_CORS_ORIGIN_REGEX", "").strip()
        self.BACKEND_CORS_ORIGIN_REGEX: Optional[str] = _cors_re or None
        
        # ========================
        # SEPAY (VietQR qr.sepay.vn + webhook tiền vào)
        # ========================
        self.SEPAY_MERCHANT_ID: str = os.getenv("SEPAY_MERCHANT_ID", "").strip()
        self.SEPAY_SECRET_KEY: str = os.getenv("SEPAY_SECRET_KEY", "").strip()
        self.SEPAY_API_URL: str = (os.getenv("SEPAY_API_URL", "https://api.sepay.vn").strip().rstrip("/") or "https://api.sepay.vn")
        self.SEPAY_REQUIRE_SIGNATURE: bool = os.getenv("SEPAY_REQUIRE_SIGNATURE", "false").lower() in ("1", "true", "yes")
        self.SEPAY_WEBHOOK_API_KEY: str = os.getenv("SEPAY_WEBHOOK_API_KEY", "").strip()
        # Khi webhook SePay để "Không chứng thực" và KHÔNG set SEPAY_WEBHOOK_API_KEY: chấp nhận nếu IP nguồn thuộc allowlist (SePay công bố).
        self.SEPAY_WEBHOOK_TRUST_NO_AUTH_IP: bool = os.getenv(
            "SEPAY_WEBHOOK_TRUST_NO_AUTH_IP", "false"
        ).lower() in ("1", "true", "yes")
        # true = đọc X-Forwarded-For + X-Real-IP dù peer không phải IP private (ví dụ hop bị báo sai).
        # Chỉ bật khi API không lộ ra internet trực tiếp — chỉ Nginx/proxy được gọi vào cổng app.
        self.SEPAY_WEBHOOK_TRUST_PROXY_HEADERS: bool = os.getenv(
            "SEPAY_WEBHOOK_TRUST_PROXY_HEADERS", "false"
        ).lower() in ("1", "true", "yes")
        _sepay_ip_env = os.getenv("SEPAY_WEBHOOK_IP_ALLOWLIST", "").strip()
        _sepay_default_ips = (
            "172.236.138.20",
            "172.233.83.68",
            "171.244.35.2",
            "151.158.108.68",
            "151.158.109.79",
            "103.255.238.139",
        )
        self.SEPAY_WEBHOOK_IP_ALLOWLIST: frozenset = frozenset(
            p.strip()
            for p in (_sepay_ip_env.split(",") if _sepay_ip_env else _sepay_default_ips)
            if p.strip()
        )
        self.SEPAY_ALLOW_INSECURE_DEV: bool = os.getenv("SEPAY_ALLOW_INSECURE_DEV", "false").lower() in ("1", "true", "yes")
        # URL đầy đủ đăng ký trên SePay (vd. Next qua ngrok: https://xxx.ngrok-free.dev/api/sepay-webhook). Để trống = {BACKEND_PUBLIC_URL}/api/v1/sepay/webhook
        self.SEPAY_WEBHOOK_PUBLIC_URL: str = os.getenv("SEPAY_WEBHOOK_PUBLIC_URL", "").strip().rstrip("/")
        self.SEPAY_QR_BANK_CODE: str = os.getenv("SEPAY_QR_BANK_CODE", "").strip()
        self.SEPAY_QR_ACCOUNT_NUMBER: str = os.getenv("SEPAY_QR_ACCOUNT_NUMBER", "").strip()
        self.SEPAY_QR_TEMPLATE: str = os.getenv("SEPAY_QR_TEMPLATE", "compact").strip() or "compact"
        self.SEPAY_CONTENT_PREFIX: str = os.getenv("SEPAY_CONTENT_PREFIX", "").strip()
        # Tiền tố nội dung CK để SePay khớp (ví dụ cấu hình dashboard: "SEVQR DH...").
        self.SEPAY_TRANSFER_PREFIX: str = os.getenv("SEPAY_TRANSFER_PREFIX", "SEVQR").strip()
        # Phần sau tiền tố: order_code (DH001) | dh_order_id (DH{order.id}, ví dụ SEVQR DH6171174772).
        self.SEPAY_TRANSFER_BODY: str = (
            os.getenv("SEPAY_TRANSFER_BODY", "order_code").strip().lower() or "order_code"
        )
        # True = nối 10 số cuối SĐT vào body (hành vi cũ; chỉ áp dụng khi SEPAY_TRANSFER_BODY=order_code).
        self.SEPAY_TRANSFER_CONTENT_LEGACY: bool = os.getenv(
            "SEPAY_TRANSFER_CONTENT_LEGACY", "false"
        ).lower() in ("1", "true", "yes")
        
        # ========================
        # NANOAI — tìm sản phẩm theo ảnh / vector text (Messaging API)
        # Bearer chỉ server; không đưa vào frontend.
        # ========================
        self.NANOAI_API_BASE: str = (
            os.getenv("NANOAI_API_BASE", "https://nanoai.vn").strip().rstrip("/") or "https://nanoai.vn"
        )
        self.NANOAI_PARTNER_ID: str = os.getenv("NANOAI_PARTNER_ID", "").strip()
        self.NANOAI_BEARER_TOKEN: str = os.getenv("NANOAI_BEARER_TOKEN", "").strip()

        # ========================
        # RATE LIMITING
        # ========================
        self.RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"
        self.RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
        self.RATE_LIMIT_OTP_PER_HOUR: int = int(os.getenv("RATE_LIMIT_OTP_PER_HOUR", "10"))
        
        # ========================
        # CACHE CONFIGURATION
        # ========================
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "300"))
        
        # ========================
        # LOGGING CONFIGURATION
        # ========================
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FILE: str = os.getenv("LOG_FILE", "app/logs/app.log")
        self.ENABLE_OTP_LOGGING: bool = os.getenv("ENABLE_OTP_LOGGING", "True").lower() == "true"
        
        # ========================
        # PERFORMANCE CONFIGURATION
        # ========================
        self.WORKER_COUNT: int = int(os.getenv("WORKER_COUNT", "4"))
        self.KEEPALIVE_SECONDS: int = int(os.getenv("KEEPALIVE_SECONDS", "5"))
        
        # ========================
        # VALIDATION & DISPLAY
        # ========================
        self._validate_and_display_status()
    
    def _validate_and_display_status(self):
        """Validate critical settings và hiển thị trạng thái"""
        print("=" * 60)
        print("🔧 CONFIGURATION STATUS CHECK")
        print("=" * 60)
        
        # Database Validation
        print("\n🗄️  DATABASE:")
        print(f"   Database URL: {self.DATABASE_URL[:60]}..." if len(self.DATABASE_URL) > 60 else f"   Database URL: {self.DATABASE_URL}")
        
        try:
            if self.IS_POSTGRESQL:
                from sqlalchemy import create_engine, text
                engine = create_engine(self.DATABASE_URL)
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                    tables = result.scalar()
                    result = conn.execute(text("SELECT COUNT(*) FROM products"))
                    product_count = result.scalar()
                print(f"   Mode: PostgreSQL (production)")
                print(f"   Tables: {tables} bảng")
                print(f"   Products: {product_count} sản phẩm")
            elif self.ACTUAL_DATABASE_PATH and self.ACTUAL_DATABASE_PATH.exists():
                import sqlite3
                size = self.ACTUAL_DATABASE_PATH.stat().st_size
                print(f"   File: {self.ACTUAL_DATABASE_PATH}")
                print(f"   Size: {size:,} bytes")
                conn = sqlite3.connect(str(self.ACTUAL_DATABASE_PATH))
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                cursor.execute("SELECT COUNT(*) FROM products")
                product_count = cursor.fetchone()[0]
                conn.close()
                print(f"   Mode: SQLite (development)")
                print(f"   Tables: {len(tables)} bảng")
                print(f"   Products: {product_count} sản phẩm")
            else:
                print("   ⚠️  Database chưa khởi tạo")
        except Exception as e:
            print(f"   ⚠️  Lỗi kết nối: {e}")
        
        # Security Validation
        print("\n🔐 SECURITY:")
        if not self.SECRET_KEY or "change-this" in self.SECRET_KEY:
            print("   ⚠️  SECRET_KEY: Đang dùng giá trị mặc định - KHÔNG AN TOÀN CHO PRODUCTION!")
        else:
            print("   ✅ SECRET_KEY: Đã cấu hình")
        
        # OTP System Validation
        print("\n📱 OTP SYSTEM:")
        print(f"   Primary Provider: {self.OTP_PRIMARY_PROVIDER}")
        print(f"   Fallback Enabled: {self.OTP_FALLBACK_ENABLED}")
        print(f"   Simulation Mode: {self.OTP_SIMULATION_MODE}")
        print(f"   OTP Length: {self.OTP_LENGTH}")
        print(f"   OTP Expire: {self.OTP_EXPIRE_MINUTES} minutes")
        
        # Zalo OTP Validation
        print("\n💬 ZALO OTP:")
        if self.ZALO_OA_ACCESS_TOKEN and len(self.ZALO_OA_ACCESS_TOKEN) > 30:
            print("   ✅ ZALO: Access Token configured")
            print(f"      OA ID: {self.ZALO_OA_ID}")
            print(f"      Register Template: {self.ZALO_TEMPLATE_REGISTER}")
            print(f"      Reset Password Template: {self.ZALO_TEMPLATE_RESET_PASSWORD}")
            print(f"      Verify Phone Template: {self.ZALO_TEMPLATE_VERIFY_PHONE}")
            print(f"      Login Template: {self.ZALO_TEMPLATE_LOGIN}")
        elif self.ZALO_OA_ACCESS_TOKEN:
            print("   ⚠️  ZALO OTP: Token quá ngắn, có thể không hợp lệ")
        else:
            print("   ⚠️  ZALO OTP: Simulation mode")
        
        # Firebase Validation
        print("\n🔥 FIREBASE:")
        firebase_configured = all([
            self.FIREBASE_PROJECT_ID,
            self.FIREBASE_CLIENT_EMAIL,
            self.FIREBASE_PRIVATE_KEY and "BEGIN PRIVATE KEY" in self.FIREBASE_PRIVATE_KEY,
            self.FIREBASE_TOKEN_URI
        ])
        
        if firebase_configured:
            print("   ✅ FIREBASE: Fully configured for production")
            print(f"      Project: {self.FIREBASE_PROJECT_ID}")
            print(f"      Client: {self.FIREBASE_CLIENT_EMAIL[:30]}...")
            print(f"      Token URI: {self.FIREBASE_TOKEN_URI}")
            print(f"      API Key: {bool(self.FIREBASE_API_KEY)}")
        else:
            print("   ⚠️  FIREBASE: Not fully configured")
            missing = []
            if not self.FIREBASE_PROJECT_ID:
                missing.append("Project ID")
            if not self.FIREBASE_CLIENT_EMAIL:
                missing.append("Client Email")
            if not self.FIREBASE_PRIVATE_KEY or "BEGIN PRIVATE KEY" not in self.FIREBASE_PRIVATE_KEY:
                missing.append("Private Key")
            if not self.FIREBASE_TOKEN_URI:
                missing.append("Token URI")
            
            if missing:
                print(f"      Missing: {', '.join(missing)}")
        
        # AI APIs
        print("\n🤖 AI APIs:")
        if self.DEEPSEEK_API_KEY:
            print("   ✅ DEEPSEEK: Configured")
        else:
            print("   ⚠️  DEEPSEEK: Not configured")
        
        if self.OPENAI_API_KEY:
            print("   ✅ OPENAI: Configured")
        else:
            print("   ⚠️  OPENAI: Not configured")
        
        # Email (for backup OTP)
        print("\n📧 EMAIL (OTP Backup):")
        if self.is_smtp_configured():
            print("   ✅ EMAIL: Configured for OTP backup")
        else:
            print("   ⚠️  EMAIL: Not configured - OTP backup unavailable")
        
        # Environment
        print("\n🌍 ENVIRONMENT:")
        print(f"   Environment: {self.ENVIRONMENT}")
        print(f"   Debug Mode: {self.DEBUG}")
        print(f"   Server: {self.SERVER_HOST}:{self.SERVER_PORT}")
        
        print("\n" + "=" * 60)
        print("📋 SUMMARY:")
        
        # Check if OTP is production ready
        otp_production_ready = (
            (self.ZALO_OA_ACCESS_TOKEN and len(self.ZALO_OA_ACCESS_TOKEN) > 30) or
            firebase_configured
        )
        
        if otp_production_ready:
            print("✅ OTP SYSTEM: READY FOR PRODUCTION")
            if firebase_configured:
                print("   Primary: Firebase Authentication")
            if self.ZALO_OA_ACCESS_TOKEN and len(self.ZALO_OA_ACCESS_TOKEN) > 30:
                print("   Fallback: Zalo OTP")
        else:
            print("❌ OTP SYSTEM: NOT PRODUCTION READY")
            print("   Run in simulation mode or configure providers")
        
        print("=" * 60)
    
    def get_otp_providers_status(self) -> Dict[str, Any]:
        """Get detailed OTP providers status for API endpoint"""
        return {
            "primary_provider": self.OTP_PRIMARY_PROVIDER,
            "fallback_enabled": self.OTP_FALLBACK_ENABLED,
            "simulation_mode": self.OTP_SIMULATION_MODE,
            "zalo_configured": bool(self.ZALO_OA_ACCESS_TOKEN and len(self.ZALO_OA_ACCESS_TOKEN) > 30),
            "firebase_configured": bool(
                self.FIREBASE_PROJECT_ID and 
                self.FIREBASE_CLIENT_EMAIL and
                self.FIREBASE_PRIVATE_KEY and 
                "BEGIN PRIVATE KEY" in self.FIREBASE_PRIVATE_KEY and
                self.FIREBASE_TOKEN_URI
            ),
            "email_backup_available": self.is_smtp_configured(),
            "rate_limits": {
                "otp_per_hour": self.RATE_LIMIT_OTP_PER_HOUR,
                "resend_delay_seconds": self.OTP_RESEND_DELAY_SECONDS,
                "daily_limit": self.OTP_DAILY_LIMIT
            }
        }
    
    def get_frontend_firebase_config(self) -> Dict[str, str]:
        """Get Firebase config for frontend"""
        return {
            "apiKey": self.FIREBASE_API_KEY,
            "authDomain": self.FIREBASE_AUTH_DOMAIN,
            "projectId": self.FIREBASE_PROJECT_ID,
            "storageBucket": self.FIREBASE_STORAGE_BUCKET,
            "messagingSenderId": self.FIREBASE_MESSAGING_SENDER_ID,
            "appId": self.FIREBASE_APP_ID
        }
    
    def is_smtp_configured(self) -> bool:
        """Giống isSmtpConfigured() bên dự án Node: host + user + pass + from."""
        from_ok = bool(
            (self.SMTP_FROM or "").strip() or (self.SENDER_EMAIL or self.EMAIL_FROM or "").strip()
        )
        return bool(
            (self.SMTP_HOST or "").strip()
            and (self.SMTP_USER or "").strip()
            and (self.SMTP_PASS or "").strip()
            and from_ok
        )

    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.ENVIRONMENT.lower() == "development"
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.ENVIRONMENT.lower() == "production"
    
    def get_upload_path(self) -> Path:
        """Get absolute upload path"""
        return Path(self.UPLOAD_DIR).absolute()
    
    def check_database_connection(self) -> Dict[str, Any]:
        """Kiểm tra kết nối database và thông tin sản phẩm"""
        result = {
            "database_url": self.DATABASE_URL[:80] + "..." if len(self.DATABASE_URL) > 80 else self.DATABASE_URL,
            "is_postgresql": self.IS_POSTGRESQL,
            "exists": False,
            "tables": 0,
            "products_count": 0,
            "products_sample": []
        }
        
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(self.DATABASE_URL)
            with engine.connect() as conn:
                if self.IS_POSTGRESQL:
                    r = conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'"))
                    result["tables"] = r.scalar()
                else:
                    r = conn.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
                    result["tables"] = r.scalar()
                
                r = conn.execute(text("SELECT COUNT(*) FROM products"))
                result["products_count"] = r.scalar()
                result["exists"] = True
                
                r = conn.execute(text("SELECT product_id, name, price FROM products LIMIT 5"))
                for row in r:
                    name = row[1] or ""
                    result["products_sample"].append({
                        "product_id": row[0],
                        "name": name[:50] + "..." if len(name) > 50 else name,
                        "price": row[2]
                    })
        except Exception as e:
            result["error"] = str(e)
        
        return result

# Global settings instance
settings = Settings()