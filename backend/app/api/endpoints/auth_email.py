"""
Đăng nhập email: OTP + magic link + thiết bị tin cậy + cookie httpOnly JWT.
Đường dẫn: /api/v1/auth/email/request | verify-otp | verify-magic
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email_identity import identity_email
from app.core.security import create_access_token
from app.crud.user import create_user, get_user_by_email, update_last_login
from app.db.session import get_db
from app.models.email_login_challenge import EmailLoginChallenge
from app.models.email_trusted_device import EmailTrustedDevice
from app.models.user import User
from app.models.user_trusted_device import UserTrustedDevice
from app.schemas.auth_email import (
    EmailAuthRequestBody,
    EmailAuthRequestResponse,
    EmailAuthVerifyOtpBody,
    EmailAuthVerifyResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.email_service import send_account_email, send_login_magic_link_email, send_login_otp_email

router = APIRouter()

_rl_email_bucket: dict[str, deque] = defaultdict(deque)
_rl_ip_bucket: dict[str, deque] = defaultdict(deque)
_email_last_send: dict[str, float] = {}
_email_send_count: dict[str, int] = {}
OTP_LENGTH = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_rl(bucket: dict, key: str, limit: int, window: float = 60.0) -> None:
    t = time.time()
    q = bucket[key]
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Quá nhiều yêu cầu. Thử lại sau vài phút.",
        )
    q.append(t)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _normalize_email(value: str) -> str:
    v = identity_email(value)
    if v:
        return v
    return (value or "").strip().lower()


def _safe_next(n: Optional[str]) -> str:
    s = (n or "").strip()
    if not s.startswith("/") or "//" in s:
        return "/"
    return s[:512]


def _browser_hash(browser_id: str) -> str:
    key = (settings.SECRET_KEY or "").encode("utf-8")
    if not key:
        key = b"dev-insecure"
    return hmac.new(key, (browser_id or "").strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _hash_otp(otp: str) -> str:
    pepper = (settings.SECRET_KEY or "dev").encode("utf-8")
    return hashlib.sha256(pepper + b":" + str(otp).strip().encode("utf-8")).hexdigest()


def _hash_magic(raw: str) -> str:
    pepper = (settings.SECRET_KEY or "dev").encode("utf-8")
    return hashlib.sha256(pepper + b":" + str(raw).strip().encode("utf-8")).hexdigest()


def _jwt_delta_minutes() -> int:
    return int(settings.EMAIL_OTP_REMEMBER_DAYS) * 24 * 60


def _set_auth_cookie(response: Response, token: str) -> None:
    max_age = _jwt_delta_minutes() * 60
    response.set_cookie(
        key=settings.AUTH_JWT_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _check_smtp() -> None:
    if not settings.is_smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình email (SMTP).",
        )


def _had_consumed_email_challenge(db: Session, email_key: str) -> bool:
    """Email đã từng hoàn tất OTP hoặc magic link (challenge có consumed_at)."""
    row = (
        db.query(EmailLoginChallenge.id)
        .filter(
            EmailLoginChallenge.email_normalized == email_key,
            EmailLoginChallenge.consumed_at.isnot(None),
        )
        .limit(1)
        .first()
    )
    return row is not None


def _auto_login_if_prior_email_challenge_consumed(
    db: Session,
    email_key: str,
    response: Response,
    next_path: str,
) -> Optional[EmailAuthRequestResponse]:
    """
    Nhánh “đã từng xác thực OTP thành công” (theo CSDL), không phụ thuộc localStorage/cookie thiết bị —
    ẩn danh vẫn có thể vào luôn nếu biết đúng email đã từng đăng nhập luồng này.
    Rủi ro: ai nhập trúng email đều có thể lấy phiên; chấp nhận theo chính sách giống NanoAI.
    """
    if not _had_consumed_email_challenge(db, email_key):
        return None
    user = get_user_by_email(db, email_key)
    if not user or not user.is_active:
        return None
    update_last_login(db, user.id)
    token = create_access_token(
        data={"sub": email_key, "user_id": user.id},
        expires_delta=timedelta(minutes=_jwt_delta_minutes()),
    )
    _set_auth_cookie(response, token)
    return EmailAuthRequestResponse(
        auto_signed_in=True,
        next=next_path,
        user=_user_response(user),
        access_token=token,
        token_type="bearer",
    )


def _try_trusted_auto_login(
    db: Session,
    email_key: str,
    browser_id: Optional[str],
    response: Response,
    next_path: str,
) -> Optional[EmailAuthRequestResponse]:
    if not browser_id or len(browser_id.strip()) < 8:
        return None
    user = get_user_by_email(db, email_key)
    if not user or not user.is_active:
        return None
    now = _now()
    h = _browser_hash(browser_id)
    # Không bắt buộc khớp email_normalized (user có thể đã chuẩn hóa email trong DB)
    row = (
        db.query(EmailTrustedDevice)
        .filter(
            EmailTrustedDevice.user_id == user.id,
            EmailTrustedDevice.browser_id_hash == h,
            EmailTrustedDevice.revoked_at.is_(None),
            EmailTrustedDevice.expires_at > now,
        )
        .first()
    )
    if not row:
        row_legacy = (
            db.query(UserTrustedDevice)
            .filter(
                UserTrustedDevice.user_id == user.id,
                UserTrustedDevice.device_token_hash == h,
            )
            .first()
        )
        if not row_legacy:
            return None
        row_legacy.last_used_at = now
        db.commit()
    else:
        row.last_used_at = now
        if row.email_normalized != email_key:
            row.email_normalized = email_key
        db.commit()
    update_last_login(db, user.id)
    token = create_access_token(
        data={"sub": email_key, "user_id": user.id},
        expires_delta=timedelta(minutes=_jwt_delta_minutes()),
    )
    _set_auth_cookie(response, token)
    return EmailAuthRequestResponse(
        auto_signed_in=True,
        next=next_path,
        user=_user_response(user),
        access_token=token,
        token_type="bearer",
    )


def _upsert_trusted_device(
    db: Session,
    user_id: int,
    email_key: str,
    browser_id: Optional[str],
    remember: bool,
) -> None:
    if not remember or not browser_id or len(browser_id.strip()) < 8:
        return
    now = _now()
    h = _browser_hash(browser_id)
    exp = now + timedelta(days=int(settings.EMAIL_TRUSTED_DEVICE_DAYS))
    row = (
        db.query(EmailTrustedDevice)
        .filter(
            EmailTrustedDevice.user_id == user_id,
            EmailTrustedDevice.browser_id_hash == h,
        )
        .first()
    )
    if row:
        row.email_normalized = email_key
        row.expires_at = exp
        row.revoked_at = None
        row.last_used_at = now
    else:
        db.add(
            EmailTrustedDevice(
                user_id=user_id,
                email_normalized=email_key,
                browser_id_hash=h,
                expires_at=exp,
            )
        )
    db.commit()
    # Đồng bộ bảng legacy (Google / OTP cũ) để /try-trusted-device vẫn khớp
    leg = (
        db.query(UserTrustedDevice)
        .filter(UserTrustedDevice.user_id == user_id, UserTrustedDevice.device_token_hash == h)
        .first()
    )
    if leg:
        leg.last_used_at = now
    else:
        db.add(UserTrustedDevice(user_id=user_id, device_token_hash=h))
    db.commit()


def _login_email_user_core(
    db: Session,
    email_key: str,
    background_tasks: BackgroundTasks,
    remember_device: bool,
    browser_id: Optional[str],
) -> Tuple[User, str]:
    user = get_user_by_email(db, email_key)
    is_first = False
    if not user:
        is_first = True
        user = create_user(
            db,
            UserCreate(
                email=email_key,
                full_name=email_key.split("@")[0],
                address=None,
                gender=None,
                phone=None,
                date_of_birth=None,
            ),
        )
        if not user:
            raise HTTPException(status_code=400, detail="Không thể tạo tài khoản")
    elif user.email != email_key:
        user.email = email_key
        db.commit()
        db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị khóa")

    update_last_login(db, user.id)
    if is_first and user.email:
        background_tasks.add_task(
            send_account_email,
            user.email,
            "Chào mừng bạn đến 188.com.vn",
            "Tài khoản email của bạn đã được đăng ký thành công.",
        )

    token = create_access_token(
        data={"sub": email_key, "user_id": user.id},
        expires_delta=timedelta(minutes=_jwt_delta_minutes()),
    )
    _upsert_trusted_device(db, user.id, email_key, browser_id, remember_device)
    return user, token


@router.post("/request", response_model=EmailAuthRequestResponse)
def email_auth_request(
    body: EmailAuthRequestBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    email_key = _normalize_email(str(body.email))
    if not email_key or "@" not in email_key:
        raise HTTPException(status_code=400, detail="Email không hợp lệ")

    next_path = _safe_next(body.next)

    ip = _client_ip(request)
    _touch_rl(_rl_ip_bucket, ip, int(settings.EMAIL_AUTH_RL_IP_PER_MINUTE))
    _touch_rl(_rl_email_bucket, email_key, int(settings.EMAIL_AUTH_RL_EMAIL_PER_MINUTE))

    auto = _auto_login_if_prior_email_challenge_consumed(db, email_key, response, next_path)
    if auto:
        return auto

    auto = _try_trusted_auto_login(db, email_key, body.browser_id, response, next_path)
    if auto:
        return auto

    _check_smtp()

    now_ts = time.time()
    last = _email_last_send.get(email_key, 0.0)
    if now_ts - last < float(settings.OTP_RESEND_DELAY_SECONDS):
        wait = int(settings.OTP_RESEND_DELAY_SECONDS - (now_ts - last)) + 1
        raise HTTPException(status_code=429, detail=f"Gửi quá nhanh. Thử lại sau {wait} giây.")

    day_key = f"{email_key}|{date.today().isoformat()}"
    cnt = _email_send_count.get(day_key, 0)
    if cnt >= int(settings.OTP_DAILY_LIMIT):
        raise HTTPException(status_code=429, detail="Đã vượt giới hạn gửi mã trong hôm nay.")

    otp = "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))
    raw_magic = secrets.token_urlsafe(32)
    exp = _now() + timedelta(minutes=int(settings.OTP_EXPIRE_MINUTES))

    db.query(EmailLoginChallenge).filter(
        EmailLoginChallenge.email_normalized == email_key,
        EmailLoginChallenge.consumed_at.is_(None),
    ).delete(synchronize_session=False)
    db.commit()

    ch = EmailLoginChallenge(
        email_normalized=email_key,
        otp_hash=_hash_otp(otp),
        magic_token_hash=_hash_magic(raw_magic),
        expires_at=exp,
    )
    db.add(ch)
    db.commit()

    api_prefix = settings.API_V1_STR.rstrip("/")
    base = settings.BACKEND_PUBLIC_URL.rstrip("/")
    q = urlencode(
        {
            "token": raw_magic,
            "email": email_key,
            "next": next_path,
            "remember": "true" if body.remember_device else "false",
        }
    )
    magic_url = f"{base}{api_prefix}/auth/email/verify-magic?{q}"

    try:
        send_login_otp_email(email_key, otp, int(settings.OTP_EXPIRE_MINUTES))
        send_login_magic_link_email(email_key, magic_url, int(settings.OTP_EXPIRE_MINUTES))
    except Exception:
        db.delete(ch)
        db.commit()
        raise HTTPException(status_code=500, detail="Không gửi được email. Thử lại sau.")

    _email_last_send[email_key] = now_ts
    _email_send_count[day_key] = cnt + 1

    return EmailAuthRequestResponse(
        auto_signed_in=False,
        next=next_path,
        message="Đã gửi mã và liên kết đăng nhập tới email. Kiểm tra cả mục thư rác.",
    )


@router.post("/verify-otp", response_model=EmailAuthVerifyResponse)
def email_auth_verify_otp(
    body: EmailAuthVerifyOtpBody,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    email_key = _normalize_email(str(body.email))
    now = _now()
    row = (
        db.query(EmailLoginChallenge)
        .filter(
            EmailLoginChallenge.email_normalized == email_key,
            EmailLoginChallenge.consumed_at.is_(None),
            EmailLoginChallenge.expires_at > now,
        )
        .order_by(EmailLoginChallenge.id.desc())
        .first()
    )
    if not row or row.otp_hash != _hash_otp(body.otp):
        raise HTTPException(status_code=400, detail="Mã OTP sai hoặc đã hết hạn")

    row.consumed_at = now
    db.commit()

    user, token = _login_email_user_core(
        db, email_key, background_tasks, body.remember_device, body.browser_id
    )
    _set_auth_cookie(response, token)
    return EmailAuthVerifyResponse(
        auto_signed_in=True,
        next=_safe_next(body.next),
        user=_user_response(user),
        access_token=token,
        token_type="bearer",
    )


def _complete_magic_or_raise(
    db: Session,
    email_key: str,
    token_raw: str,
    background_tasks: BackgroundTasks,
    remember_device: bool,
    browser_id: Optional[str],
) -> Tuple[User, str]:
    now = _now()
    mh = _hash_magic(token_raw)
    row = (
        db.query(EmailLoginChallenge)
        .filter(
            EmailLoginChallenge.email_normalized == email_key,
            EmailLoginChallenge.magic_token_hash == mh,
            EmailLoginChallenge.consumed_at.is_(None),
            EmailLoginChallenge.expires_at > now,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="Liên kết không hợp lệ hoặc đã hết hạn")
    row.consumed_at = now
    db.commit()
    return _login_email_user_core(db, email_key, background_tasks, remember_device, browser_id)


@router.get("/verify-magic")
def email_auth_verify_magic(
    token: str,
    email: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    next: Optional[str] = None,
    remember: Optional[str] = None,
):
    email_key = _normalize_email(email)
    if not email_key or "@" not in email_key:
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    remember_device = str(remember or "").lower() in ("1", "true", "yes")
    # Magic link mở trong trình duyệt: không có browser_id → không ghi thiết bị tin cậy trừ khi sau này bổ sung cookie phụ
    user, jwt_tok = _complete_magic_or_raise(
        db, email_key, token, background_tasks, remember_device, browser_id=None
    )
    dest = settings.FRONTEND_BASE_URL.rstrip("/") + _safe_next(next)
    r = RedirectResponse(url=dest, status_code=status.HTTP_302_FOUND)
    _set_auth_cookie(r, jwt_tok)
    return r