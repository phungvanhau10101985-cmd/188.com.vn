# backend/app/api/endpoints/auth.py - FINAL FIXED VERSION + OTP
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import date, timedelta, datetime, timezone
import random
import string
import time
import hashlib
import hmac
import requests

from app.db.session import get_db
from app.core.config import settings
from app.core.security import create_access_token, get_current_user, create_admin_token
from app.schemas.user import (
    UserCreate, UserResponse, UserLogin, Token,
    UserUpdate, DateOfBirthResponse, SendRegisterOtpRequest, ForgotDateOfBirthRequest,
    GoogleLoginRequest, SendEmailOtpRequest, VerifyEmailOtpRequest,
    TryTrustedDeviceRequest, TryTrustedDeviceResponse,
)
from app.schemas.admin import AdminTokenResponse
from app.models.admin import AdminUser
from app.core.admin_permissions import effective_module_keys
from app.core.email_identity import identity_email
from app.crud.user import (
    get_user_by_phone, create_user, update_user,
    update_last_login, get_user_by_email
)
from app import crud as app_crud
from app.services.email_service import send_account_email, send_login_otp_email
from app.services.user_public_response import user_response_with_linked_admin
from app.models.user import User
from app.models.user_trusted_device import UserTrustedDevice
from app.api.endpoints.auth_email import router as auth_email_router

router = APIRouter()
router.include_router(auth_email_router, prefix="/email", tags=["authentication"])

# In-memory OTP store: phone -> { "code": str, "expires_at": datetime }
_otp_store: dict = {}
# OTP cho quên ngày sinh (tách riêng để không trùng với OTP đăng ký)
_forgot_dob_otp_store: dict = {}
# Email OTP: email (lower) -> { "code": str, "expires_at": datetime }
_email_otp_store: dict = {}
# Giới hạn tần suất gửi OTP email: email (lower) -> unix time lần gửi gần nhất
_email_last_send: dict = {}
# Số lần gửi theo email + ngày (key f"{email}|{YYYY-MM-DD}")
_email_send_count: dict = {}
OTP_EXPIRE_MINUTES = 10
OTP_LENGTH_EMAIL = 6
# Zalo: 4 số. Firebase (tin nhắn): 6 số.
OTP_LENGTH_ZALO = 4
OTP_LENGTH_FIREBASE = 6


def _normalize_phone(phone: str) -> str:
    p = str(phone).strip()
    if not p.startswith("0"):
        p = "0" + p.lstrip("+84")
    return p[:11]


def _generate_otp(length: int = OTP_LENGTH_ZALO) -> str:
    return "".join(random.choices(string.digits, k=length))


def _store_otp(phone: str, code: str) -> None:
    from datetime import timedelta
    expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    _otp_store[phone] = {"code": code, "expires_at": expires}


def _verify_otp(phone: str, code: str) -> bool:
    key = _normalize_phone(phone)
    if key not in _otp_store:
        return False
    entry = _otp_store[key]
    if datetime.now(timezone.utc) > entry["expires_at"]:
        del _otp_store[key]
        return False
    if entry["code"] != str(code).strip():
        return False
    del _otp_store[key]
    return True


def _store_forgot_dob_otp(phone: str, code: str) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRE_MINUTES)
    _forgot_dob_otp_store[phone] = {"code": code, "expires_at": expires}


def _verify_forgot_dob_otp(phone: str, code: str) -> bool:
    key = _normalize_phone(phone)
    if key not in _forgot_dob_otp_store:
        return False
    entry = _forgot_dob_otp_store[key]
    if datetime.now(timezone.utc) > entry["expires_at"]:
        del _forgot_dob_otp_store[key]
        return False
    if entry["code"] != str(code).strip():
        return False
    del _forgot_dob_otp_store[key]
    return True


def _normalize_email(value: str) -> str:
    """Một hộp Gmail/OTP = một chuỗi (dù chọn đăng nhập Google hay mã email)."""
    v = identity_email(value)
    if v:
        return v
    return (value or "").strip().lower()


def _store_email_otp(email_key: str, code: str) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    _email_otp_store[email_key] = {"code": str(code), "expires_at": expires}


def _verify_email_otp(email: str, code: str) -> bool:
    key = _normalize_email(email)
    if key not in _email_otp_store:
        return False
    entry = _email_otp_store[key]
    if datetime.now(timezone.utc) > entry["expires_at"]:
        del _email_otp_store[key]
        return False
    if entry["code"] != str(code).strip():
        return False
    del _email_otp_store[key]
    return True


def _check_email_smtp_config() -> None:
    if not settings.is_smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Máy chủ chưa cấu hình email (SMTP). Hỏi quản trị viên.",
        )


def _device_token_hash(device_id: str) -> str:
    key = (settings.SECRET_KEY or "").encode("utf-8")
    if not key:
        key = b"dev-insecure"
    return hmac.new(key, (device_id or "").strip().encode("utf-8"), hashlib.sha256).hexdigest()


def _register_trusted_device(db: Session, user_id: int, device_id: Optional[str]) -> None:
    if not device_id or len((device_id or "").strip()) < 8:
        return
    h = _device_token_hash(device_id)
    row = (
        db.query(UserTrustedDevice)
        .filter(UserTrustedDevice.user_id == user_id, UserTrustedDevice.device_token_hash == h)
        .first()
    )
    if row:
        row.last_used_at = datetime.now(timezone.utc)
    else:
        db.add(UserTrustedDevice(user_id=user_id, device_token_hash=h))
    db.commit()


def _firebase_fallback_send(phone: str, code: str) -> bool:
    """Fallback gửi OTP qua Firebase (webhook Cloud Function hoặc mô phỏng)."""
    url = (settings.FIREBASE_OTP_WEBHOOK_URL or "").strip()
    if url:
        try:
            r = requests.post(url, json={"phone": phone, "otp": code}, timeout=10)
            return r.status_code == 200
        except Exception:
            return False
    # Không cấu hình webhook: mô phỏng gửi (log để test)
    print(f"[Firebase fallback] OTP cho {phone}: {code}")
    return True


@router.post("/send-register-otp")
def send_register_otp(body: SendRegisterOtpRequest, db: Session = Depends(get_db)):
    """Deprecated: đăng ký bằng phone/DOB không còn hỗ trợ."""
    raise HTTPException(status_code=410, detail="Đăng ký bằng số điện thoại không còn hỗ trợ. Vui lòng đăng nhập Gmail.")
    phone = _normalize_phone(body.phone)
    if len(phone) < 10 or not phone[1:].isdigit():
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ")
    existing = get_user_by_phone(db, phone)
    if existing:
        raise HTTPException(status_code=400, detail="Số điện thoại đã được đăng ký")
    code = _generate_otp(OTP_LENGTH_ZALO)
    _store_otp(phone, code)

    # Ưu tiên Zalo (4 số)
    try:
        from app.services.zalo_otp_service import get_zalo_otp_service
        zalo = get_zalo_otp_service()
        result = zalo.send_otp(phone, code, "register")
        if result.get("success") or result.get("zalo_sent"):
            return {
                "message": "Mã OTP đã gửi qua Zalo",
                "phone": phone,
                "provider": "zalo",
                "fallback_used": False,
            }
    except Exception:
        pass

    # Fallback Firebase: dùng mã 6 số
    code = _generate_otp(OTP_LENGTH_FIREBASE)
    _store_otp(phone, code)
    fb_ok = _firebase_fallback_send(phone, code)
    return {
        "message": "Mã OTP đã gửi qua Firebase" if fb_ok else "Gửi Zalo thất bại, đã thử Firebase",
        "phone": phone,
        "provider": "firebase",
        "fallback_used": True,
    }


@router.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Deprecated: đăng ký bằng phone/DOB không còn hỗ trợ."""
    raise HTTPException(status_code=410, detail="Đăng ký bằng số điện thoại không còn hỗ trợ. Vui lòng đăng nhập Gmail.")

@router.post("/login", response_model=Token)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    """Deprecated: đăng nhập bằng số điện thoại không còn hỗ trợ."""
    raise HTTPException(status_code=410, detail="Đăng nhập bằng số điện thoại không còn hỗ trợ. Vui lòng đăng nhập Gmail.")


@router.post("/try-trusted-device", response_model=TryTrustedDeviceResponse)
def try_trusted_device_login(body: TryTrustedDeviceRequest, db: Session = Depends(get_db)):
    """
    Nếu email + mã thiết bị (localStorage) đã lưu sau lần OTP thành công trước đó → cấp JWT, không cần OTP.
    Mỗi trình duyệt có mã thiết bị riêng; Chrome ≠ Edge.
    """
    device_id = (body.device_id or "").strip()
    if len(device_id) < 8:
        return TryTrustedDeviceResponse(ok=False, require_otp=True)
    email_key = _normalize_email(str(body.email))
    user = get_user_by_email(db, email_key)
    if not user or not user.is_active:
        return TryTrustedDeviceResponse(ok=False, require_otp=True)
    row = (
        db.query(UserTrustedDevice)
        .filter(
            UserTrustedDevice.user_id == user.id,
            UserTrustedDevice.device_token_hash == _device_token_hash(device_id),
        )
        .first()
    )
    if not row:
        return TryTrustedDeviceResponse(ok=False, require_otp=True)
    row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    update_last_login(db, user.id)
    minutes = int(settings.EMAIL_OTP_REMEMBER_DAYS) * 24 * 60
    access_token = create_access_token(
        data={"sub": email_key, "user_id": user.id},
        expires_delta=timedelta(minutes=minutes),
    )
    return TryTrustedDeviceResponse(
        ok=True,
        require_otp=False,
        access_token=access_token,
        token_type="bearer",
        user=user_response_with_linked_admin(db, user),
    )


@router.post("/send-email-otp")
def send_email_login_otp(body: SendEmailOtpRequest):
    """Gửi mã OTP tới email để đăng nhập/đăng ký. Cần cấu hình SMTP."""
    _check_email_smtp_config()
    email_key = _normalize_email(str(body.email))
    if not email_key or "@" not in email_key:
        raise HTTPException(status_code=400, detail="Email không hợp lệ")

    now = time.time()
    last = _email_last_send.get(email_key, 0.0)
    if now - last < float(settings.OTP_RESEND_DELAY_SECONDS):
        wait = int(settings.OTP_RESEND_DELAY_SECONDS - (now - last)) + 1
        raise HTTPException(status_code=429, detail=f"Gửi quá nhanh. Thử lại sau {wait} giây.")

    day_key = f"{email_key}|{date.today().isoformat()}"
    cnt = _email_send_count.get(day_key, 0)
    if cnt >= int(settings.OTP_DAILY_LIMIT):
        raise HTTPException(status_code=429, detail="Đã vượt giới hạn gửi mã trong hôm nay. Thử lại ngày mai.")

    code = "".join(random.choices(string.digits, k=OTP_LENGTH_EMAIL))
    _store_email_otp(email_key, code)

    try:
        send_login_otp_email(email_key, code, int(settings.OTP_EXPIRE_MINUTES))
    except Exception:
        if email_key in _email_otp_store:
            del _email_otp_store[email_key]
        raise HTTPException(
            status_code=500,
            detail="Không gửi được email. Kiểm tra SMTP hoặc thử lại sau.",
        )

    _email_last_send[email_key] = now
    _email_send_count[day_key] = cnt + 1
    return {
        "message": "Đã gửi mã tới email. Kiểm tra cả mục thư rác.",
        "email": email_key,
    }


@router.post("/verify-email-otp", response_model=Token)
def verify_email_login_otp(
    body: VerifyEmailOtpRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Xác nhận mã email → tạo/đăng nhập tài khoản. JWT có thời hạn theo EMAIL_OTP_REMEMBER_DAYS (mặc định 365 ngày)."""
    email_key = _normalize_email(str(body.email))
    if not _verify_email_otp(email_key, body.code):
        raise HTTPException(status_code=400, detail="Mã OTP sai hoặc đã hết hạn")

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
        # Chuẩn hóa cột email (bản cũ trước khi có identity) về cùng key với Google/OTP
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

    minutes = int(settings.EMAIL_OTP_REMEMBER_DAYS) * 24 * 60
    access_token = create_access_token(
        data={"sub": email_key, "user_id": user.id},
        expires_delta=timedelta(minutes=minutes),
    )
    _register_trusted_device(db, user.id, body.device_id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response_with_linked_admin(db, user),
    }


@router.post("/google", response_model=Token)
def google_login(
    body: GoogleLoginRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Đăng nhập Google OAuth (chỉ @gmail.com)"""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID chưa được cấu hình")
    try:
        resp = requests.get(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": body.id_token},
            timeout=5
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token không hợp lệ")
        token_info = resp.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Không thể xác minh Google token")

    aud = token_info.get("aud")
    email = identity_email((token_info.get("email") or ""))
    email_verified = token_info.get("email_verified")

    if aud != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google token không đúng ứng dụng")
    if email_verified not in ("true", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email chưa được xác minh")
    if not email or "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email không hợp lệ từ Google")
    if not email.endswith("@gmail.com"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ hỗ trợ đăng nhập Gmail")

    user = get_user_by_email(db, email)
    is_first_login = False
    if not user:
        is_first_login = True
        user_data = UserCreate(
            email=email,
            full_name=token_info.get("name"),
            address=None,
            gender=None,
            phone=None,
            date_of_birth=None,
        )
        user = create_user(db, user_data)
        if not user:
            raise HTTPException(status_code=400, detail="Không thể tạo tài khoản")
        user.avatar = token_info.get("picture")
        user.is_verified = True
        db.commit()
        db.refresh(user)
    elif user.email != email:
        user.email = email
        if token_info.get("picture") and not user.avatar:
            user.avatar = token_info.get("picture")
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tài khoản đã bị khóa")

    update_last_login(db, user.id)

    _register_trusted_device(db, user.id, body.device_id)

    if is_first_login:
        background_tasks.add_task(
            send_account_email,
            email,
            "Chào mừng bạn đến 188.com.vn",
            "Tài khoản Gmail của bạn đã được đăng ký thành công.",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": email, "user_id": user.id},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_response_with_linked_admin(db, user),
    }

@router.post("/send-forgot-dob-otp")
def send_forgot_dob_otp(body: SendRegisterOtpRequest, db: Session = Depends(get_db)):
    """Deprecated: quên ngày sinh không còn hỗ trợ."""
    raise HTTPException(status_code=410, detail="Chức năng này không còn hỗ trợ. Vui lòng đăng nhập Gmail.")


@router.post("/forgot-date-of-birth", response_model=DateOfBirthResponse)
def forgot_date_of_birth(body: ForgotDateOfBirthRequest, db: Session = Depends(get_db)):
    """Deprecated: quên ngày sinh không còn hỗ trợ."""
    raise HTTPException(status_code=410, detail="Chức năng này không còn hỗ trợ. Vui lòng đăng nhập Gmail.")

@router.post("/admin-session-token", response_model=AdminTokenResponse)
def issue_admin_token_for_linked_customer(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Khách đã đăng nhập có admin_users.linked_user_id → cấp JWT admin (giống đăng nhập /admin/login).
    """
    admin_row = (
        db.query(AdminUser)
        .filter(
            AdminUser.linked_user_id == current_user.id,
            AdminUser.is_active.is_(True),
        )
        .first()
    )
    if not admin_row:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản không được gán quyền quản trị.",
        )
    app_crud.update_admin_last_login(db, admin_row.id)
    db.refresh(admin_row)
    token = create_admin_token(admin_row.id)
    role_value = admin_row.role.value if hasattr(admin_row.role, "value") else str(admin_row.role)
    return AdminTokenResponse(
        access_token=token,
        token_type="bearer",
        admin_id=admin_row.id,
        username=admin_row.username,
        role=role_value,
        modules=effective_module_keys(admin_row, db),
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lấy thông tin user hiện tại"""
    return user_response_with_linked_admin(db, current_user)

@router.put("/me", response_model=UserResponse)
def update_current_user_info(
    user_update: UserUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cập nhật thông tin user (trừ số điện thoại)."""
    updated_user = update_user(db, current_user.id, user_update)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy user"
        )
    if updated_user and updated_user.email:
        background_tasks.add_task(
            send_account_email,
            updated_user.email,
            "Cập nhật thông tin tài khoản",
            "Thông tin tài khoản của bạn đã được cập nhật.",
        )
    return user_response_with_linked_admin(db, updated_user)