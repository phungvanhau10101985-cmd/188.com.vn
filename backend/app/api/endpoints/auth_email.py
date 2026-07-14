"""
Đăng nhập email: OTP + thiết bị tin cậy + cookie httpOnly JWT.
Đường dẫn: /api/v1/auth/email/request | verify-otp | verify-magic
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.email_identity import identity_email
from app.core.security import create_access_token, get_current_user
from app.crud.user import create_user, get_user_by_email, update_last_login
from app.db.session import get_db
from app.models.email_login_challenge import EmailLoginChallenge
from app.models.email_trusted_device import EmailTrustedDevice
from app.models.user import User
from app.schemas.auth_email import (
    EmailAuthRequestBody,
    EmailAuthRequestResponse,
    EmailAuthVerifyOtpBody,
    EmailAuthVerifyResponse,
)
from app.schemas.user import UserCreate, UserResponse
from app.services.email_service import send_account_email, send_login_otp_email
from app.services.auth_challenge import acquire_otp_issue_lock
from app.services.user_public_response import user_response_with_linked_admin

router = APIRouter()

_rl_email_bucket: dict[str, deque] = defaultdict(deque)
_rl_ip_bucket: dict[str, deque] = defaultdict(deque)
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
        raise RuntimeError("SECRET_KEY chưa được cấu hình.")
    return hmac.new(key, (browser_id or "").strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _hash_otp(otp: str) -> str:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY chưa được cấu hình.")
    pepper = settings.SECRET_KEY.encode("utf-8")
    return hashlib.sha256(pepper + b":" + str(otp).strip().encode("utf-8")).hexdigest()


def _hash_magic(raw: str) -> str:
    if not settings.SECRET_KEY:
        raise RuntimeError("SECRET_KEY chưa được cấu hình.")
    pepper = settings.SECRET_KEY.encode("utf-8")
    return hashlib.sha256(pepper + b":" + str(raw).strip().encode("utf-8")).hexdigest()


def _jwt_delta_minutes() -> int:
    session_days = min(
        int(settings.EMAIL_OTP_REMEMBER_DAYS),
        int(settings.EMAIL_TRUSTED_DEVICE_DAYS),
    )
    return max(1, session_days) * 24 * 60


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


def _set_trusted_device_cookie(response: Response, token: str) -> None:
    max_age = int(settings.EMAIL_TRUSTED_DEVICE_DAYS) * 24 * 60 * 60
    response.set_cookie(
        key=settings.AUTH_TRUSTED_DEVICE_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )


def _user_response(db: Session, user: User) -> UserResponse:
    return user_response_with_linked_admin(db, user)


def _check_smtp() -> None:
    if not settings.is_smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình email (SMTP).",
        )


def _try_trusted_auto_login(
    db: Session,
    email_key: str,
    trusted_token: Optional[str],
    response: Response,
    next_path: str,
) -> Optional[EmailAuthRequestResponse]:
    if not trusted_token or len(trusted_token.strip()) < 32:
        return None
    user = get_user_by_email(db, email_key)
    if not user or not user.is_active:
        return None
    now = _now()
    token_hash = _hash_magic(trusted_token)
    row = (
        db.query(EmailTrustedDevice)
        .filter(
            EmailTrustedDevice.user_id == user.id,
            EmailTrustedDevice.token_hash == token_hash,
            EmailTrustedDevice.revoked_at.is_(None),
            EmailTrustedDevice.expires_at > now,
        )
        .first()
    )
    if not row:
        return None
    row.last_used_at = now
    if row.email_normalized != email_key:
        row.email_normalized = email_key
    db.commit()
    update_last_login(db, user.id)
    token = create_access_token(
        data={
            "sub": email_key,
            "user_id": user.id,
            "auth_time": int(now.timestamp()),
            "amr": ["trusted_device"],
        },
        expires_delta=timedelta(minutes=_jwt_delta_minutes()),
    )
    _set_auth_cookie(response, token)
    return EmailAuthRequestResponse(
        auto_signed_in=True,
        next=next_path,
        user=_user_response(db, user),
        access_token=token,
        token_type="bearer",
    )


def _upsert_trusted_device(
    db: Session,
    user_id: int,
    email_key: str,
    browser_id: Optional[str],
    remember: bool,
) -> Optional[str]:
    if not remember or not browser_id or len(browser_id.strip()) < 8:
        return None
    now = _now()
    h = _browser_hash(browser_id)
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_magic(raw_token)
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
        row.token_hash = token_hash
        row.expires_at = exp
        row.revoked_at = None
        row.last_used_at = now
    else:
        db.add(
            EmailTrustedDevice(
                user_id=user_id,
                email_normalized=email_key,
                browser_id_hash=h,
                token_hash=token_hash,
                expires_at=exp,
            )
        )
    db.commit()
    return raw_token


def _login_email_user_core(
    db: Session,
    email_key: str,
    background_tasks: BackgroundTasks,
    remember_device: bool,
    browser_id: Optional[str],
) -> Tuple[User, str, Optional[str]]:
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
        data={
            "sub": email_key,
            "user_id": user.id,
            "auth_time": int(_now().timestamp()),
            "amr": ["otp"],
        },
        expires_delta=timedelta(minutes=_jwt_delta_minutes()),
    )
    trusted_token = _upsert_trusted_device(db, user.id, email_key, browser_id, remember_device)
    return user, token, trusted_token


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

    auto = _try_trusted_auto_login(
        db,
        email_key,
        request.cookies.get(settings.AUTH_TRUSTED_DEVICE_COOKIE_NAME),
        response,
        next_path,
    )
    if auto:
        return auto

    _check_smtp()

    now = _now()
    ip_hash = _hash_magic(ip)
    for lock_key in sorted((f"email-login:{email_key}", f"email-login-ip:{ip_hash}")):
        acquire_otp_issue_lock(db, lock_key)
    latest = (
        db.query(EmailLoginChallenge)
        .filter(EmailLoginChallenge.email_normalized == email_key)
        .order_by(EmailLoginChallenge.id.desc())
        .first()
    )
    if latest and latest.created_at:
        created = latest.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = (now - created).total_seconds()
        if age < float(settings.OTP_RESEND_DELAY_SECONDS):
            wait = int(settings.OTP_RESEND_DELAY_SECONDS - age) + 1
            raise HTTPException(status_code=429, detail=f"Gửi quá nhanh. Thử lại sau {wait} giây.")
    email_minute_count = (
        db.query(EmailLoginChallenge.id)
        .filter(
            EmailLoginChallenge.email_normalized == email_key,
            EmailLoginChallenge.created_at >= now - timedelta(minutes=1),
        )
        .count()
    )
    ip_minute_count = (
        db.query(EmailLoginChallenge.id)
        .filter(
            EmailLoginChallenge.request_ip_hash == ip_hash,
            EmailLoginChallenge.created_at >= now - timedelta(minutes=1),
        )
        .count()
    )
    if email_minute_count >= int(settings.EMAIL_AUTH_RL_EMAIL_PER_MINUTE) or ip_minute_count >= int(
        settings.EMAIL_AUTH_RL_IP_PER_MINUTE
    ):
        raise HTTPException(status_code=429, detail="Quá nhiều yêu cầu OTP. Thử lại sau một phút.")
    daily_count = (
        db.query(EmailLoginChallenge.id)
        .filter(
            EmailLoginChallenge.email_normalized == email_key,
            EmailLoginChallenge.created_at >= now - timedelta(days=1),
        )
        .count()
    )
    if daily_count >= int(settings.OTP_DAILY_LIMIT):
        raise HTTPException(status_code=429, detail="Đã vượt giới hạn gửi mã trong hôm nay.")

    otp = "".join(secrets.choice(string.digits) for _ in range(OTP_LENGTH))
    exp = _now() + timedelta(minutes=int(settings.OTP_EXPIRE_MINUTES))

    db.query(EmailLoginChallenge).filter(
        EmailLoginChallenge.email_normalized == email_key,
        EmailLoginChallenge.consumed_at.is_(None),
    ).delete(synchronize_session=False)

    ch = EmailLoginChallenge(
        email_normalized=email_key,
        request_ip_hash=ip_hash,
        otp_hash=_hash_otp(otp),
        # Cột này vẫn bắt buộc để giữ tương thích schema, nhưng request mới không gửi magic link.
        magic_token_hash=_hash_magic(secrets.token_urlsafe(32)),
        expires_at=exp,
    )
    db.add(ch)
    db.commit()

    try:
        send_login_otp_email(email_key, otp, int(settings.OTP_EXPIRE_MINUTES))
    except Exception:
        db.delete(ch)
        db.commit()
        raise HTTPException(status_code=500, detail="Không gửi được email. Thử lại sau.")

    return EmailAuthRequestResponse(
        auto_signed_in=False,
        next=next_path,
        message="Đã gửi mã OTP tới email. Làm mới hộp thư nếu chưa thấy; kiểm tra cả thư rác.",
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
    if not row:
        raise HTTPException(status_code=400, detail="Mã OTP sai hoặc đã hết hạn")
    if int(row.attempts or 0) >= int(settings.OTP_MAX_RETRIES):
        raise HTTPException(status_code=429, detail="Mã OTP đã bị khóa do nhập sai quá nhiều lần")
    if not secrets.compare_digest(row.otp_hash, _hash_otp(body.otp)):
        db.query(EmailLoginChallenge).filter(
            EmailLoginChallenge.id == row.id,
            EmailLoginChallenge.consumed_at.is_(None),
        ).update(
            {EmailLoginChallenge.attempts: func.coalesce(EmailLoginChallenge.attempts, 0) + 1},
            synchronize_session=False,
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Mã OTP sai hoặc đã hết hạn")
    updated = (
        db.query(EmailLoginChallenge)
        .filter(
            EmailLoginChallenge.id == row.id,
            EmailLoginChallenge.consumed_at.is_(None),
            EmailLoginChallenge.expires_at > now,
            func.coalesce(EmailLoginChallenge.attempts, 0) < int(settings.OTP_MAX_RETRIES),
        )
        .update({EmailLoginChallenge.consumed_at: now}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Mã OTP đã được sử dụng hoặc hết hạn")
    db.commit()

    user, token, trusted_token = _login_email_user_core(
        db, email_key, background_tasks, body.remember_device, body.browser_id
    )
    _set_auth_cookie(response, token)
    if trusted_token:
        _set_trusted_device_cookie(response, trusted_token)
    return EmailAuthVerifyResponse(
        auto_signed_in=True,
        next=_safe_next(body.next),
        user=_user_response(db, user),
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
) -> Tuple[User, str, Optional[str]]:
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
    updated = (
        db.query(EmailLoginChallenge)
        .filter(
            EmailLoginChallenge.id == row.id,
            EmailLoginChallenge.consumed_at.is_(None),
            EmailLoginChallenge.expires_at > now,
        )
        .update({EmailLoginChallenge.consumed_at: now}, synchronize_session=False)
    )
    if updated != 1:
        db.rollback()
        raise HTTPException(status_code=400, detail="Liên kết đã được sử dụng hoặc hết hạn")
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
    user, jwt_tok, trusted_token = _complete_magic_or_raise(
        db, email_key, token, background_tasks, remember_device, browser_id=None
    )
    dest = settings.FRONTEND_BASE_URL.rstrip("/") + _safe_next(next)
    r = RedirectResponse(url=dest, status_code=status.HTTP_302_FOUND)
    _set_auth_cookie(r, jwt_tok)
    if trusted_token:
        _set_trusted_device_cookie(r, trusted_token)
    return r


@router.post("/trusted-device/revoke")
def revoke_current_trusted_device(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = request.cookies.get(settings.AUTH_TRUSTED_DEVICE_COOKIE_NAME)
    if raw:
        row = (
            db.query(EmailTrustedDevice)
            .filter(
                EmailTrustedDevice.user_id == current_user.id,
                EmailTrustedDevice.token_hash == _hash_magic(raw),
                EmailTrustedDevice.revoked_at.is_(None),
            )
            .first()
        )
        if row:
            row.revoked_at = _now()
            db.commit()
    response.delete_cookie(
        key=settings.AUTH_TRUSTED_DEVICE_COOKIE_NAME,
        path="/",
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
    )
    return {"ok": True}