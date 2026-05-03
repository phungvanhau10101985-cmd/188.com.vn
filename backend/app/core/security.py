# backend/app/core/security.py - FIXED VERSION
from datetime import datetime, timedelta
from typing import Literal, Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app import crud
from app.models.user import User
from app.models.admin import AdminUser, AdminRole
from app.core.admin_permissions import admin_allowed_operation, http_method_to_admin_crud_need

_PRIVILEGED_ADMIN_ROLES = frozenset({AdminRole.SUPER_ADMIN, AdminRole.ADMIN})

# Dùng bcrypt trực tiếp (tránh lỗi passlib + bcrypt 4.1+)
def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or not plain_password:
        return False
    try:
        plain = plain_password.encode("utf-8")[:72] if isinstance(plain_password, str) else plain_password
        if isinstance(hashed_password, str):
            h = hashed_password.strip().encode("utf-8")
        else:
            h = hashed_password
        if not h or not h.startswith(b"$2"):
            return False
        return bcrypt.checkpw(plain, h)
    except Exception:
        return False

# OAuth2 scheme for users (OpenAPI / legacy)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/google")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/google", auto_error=False)

http_bearer_optional = HTTPBearer(auto_error=False)


def get_raw_token(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_optional),
) -> str:
    """JWT từ header Bearer hoặc cookie httpOnly (luồng đăng nhập email mới)."""
    if creds and creds.credentials:
        return creds.credentials.strip()
    name = getattr(settings, "AUTH_JWT_COOKIE_NAME", "188_access_token")
    raw = request.cookies.get(name)
    if raw:
        return raw.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_raw_token_optional(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer_optional),
) -> Optional[str]:
    if creds and creds.credentials:
        return creds.credentials.strip()
    name = getattr(settings, "AUTH_JWT_COOKIE_NAME", "188_access_token")
    raw = request.cookies.get(name)
    return raw.strip() if raw else None

# OAuth2 scheme for admin
admin_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/admin/login",
    scheme_name="AdminAuth"
)

def _get_secret_key() -> str:
    """Lấy SECRET_KEY từ config; bắt buộc phải cấu hình khi deploy."""
    key = getattr(settings, "SECRET_KEY", "") or ""
    if not key or key == "your-secret-key-change-in-production" or "change-this" in (key or ""):
        raise ValueError(
            "SECRET_KEY chưa được cấu hình. Đặt SECRET_KEY trong .env trước khi chạy production."
        )
    return key

def verify_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_current_user(
    token: str = Depends(get_raw_token),
    db: Session = Depends(get_db)
) -> User:
    """Get current user from token - FIXED VERSION"""
    payload = verify_token(token)
    
    # FIX: Get both user_id and phone from payload
    user_id = payload.get("user_id")  # Integer ID (if available)
    user_identifier = payload.get("sub")   # Email or phone
    token_type: str = payload.get("type")
    
    if not user_identifier:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    if token_type != "user":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    # FIX: Try to find user by ID first, then by phone
    user = None
    
    # Method 1: Try by user_id (if available in token)
    if user_id:
        try:
            user = crud.user.get_user(db, user_id=int(user_id))
        except (ValueError, TypeError):
            # user_id might not be a valid integer
            pass
    
    # Method 2: If not found by ID, try by identifier
    if not user and user_identifier:
        if "@" in user_identifier:
            user = crud.user.get_user_by_email(db, email=user_identifier)
        else:
            user = crud.user.get_user_by_phone(db, phone=user_identifier)
    
    # Method 3: Try to find by any possible identifier
    if not user:
        try:
            possible_id = int(user_identifier)
            user = crud.user.get_user(db, user_id=possible_id)
        except (ValueError, TypeError):
            pass
    
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return user


def get_current_user_optional(
    token: Optional[str] = Depends(get_raw_token_optional),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Lấy user hiện tại nếu có token hợp lệ; không có token hoặc token lỗi thì trả về None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get("user_id")
    user_identifier = payload.get("sub")
    token_type = payload.get("type")
    if not user_identifier or token_type != "user":
        return None
    user = None
    if user_id:
        try:
            user = crud.user.get_user(db, user_id=int(user_id))
        except (ValueError, TypeError):
            pass
    if not user and user_identifier:
        if "@" in user_identifier:
            user = crud.user.get_user_by_email(db, email=user_identifier)
        else:
            user = crud.user.get_user_by_phone(db, phone=user_identifier)
    return user


# ========== ADMIN FUNCTIONS ==========
def get_current_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: Session = Depends(get_db)
) -> AdminUser:
    """Get current admin from token"""
    payload = verify_token(token)
    admin_id: str = payload.get("sub")
    token_type: str = payload.get("type")
    
    if admin_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    if token_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    
    try:
        admin = crud.admin.get_admin(db, admin_id=int(admin_id))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin ID",
        )
    
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found",
        )
    
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin account is inactive",
        )
    
    return admin


def require_privileged_admin(
    admin: AdminUser = Depends(get_current_admin),
) -> AdminUser:
    """Chỉ super_admin / admin — cấu hình hệ thống, thành viên, ngân hàng, gán quyền."""
    if admin.role not in _PRIVILEGED_ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ quản trị viên chính (super_admin/admin) được thực hiện thao tác này.",
        )
    return admin


def require_super_admin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Chỉ super_admin — chỉnh preset vai trò NV, tài khoản super_admin…"""
    if admin.role != AdminRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ super_admin được thực hiện thao tác này.",
        )
    return admin


def require_module_permission(
    module_key: str,
    *,
    need: Optional[Literal["view", "create", "update", "delete"]] = None,
):
    """Kiểm tra quyền mục theo preset/granular; thao tác suy từ HTTP method nếu không chỉ định."""

    def dep(
        request: Request,
        admin: AdminUser = Depends(get_current_admin),
        db: Session = Depends(get_db),
    ) -> AdminUser:
        op = need if need is not None else http_method_to_admin_crud_need(request.method)
        if not admin_allowed_operation(admin, db, module_key, op):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Không có quyền thao tác « {module_key} » ({op}).",
            )
        return admin

    return dep


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT token for regular users"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Ensure token has required fields
    if "sub" not in to_encode:
        raise ValueError("Token data must contain 'sub' field")
    
    to_encode.update({
        "exp": expire,
        "type": "user"  # Add token type for user
    })
    
    encoded_jwt = jwt.encode(to_encode, _get_secret_key(), algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_admin_token(admin_id: int) -> str:
    """Create JWT token for admin"""
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    
    to_encode = {
        "sub": str(admin_id),
        "type": "admin",
        "exp": expire
    }
    
    encoded_jwt = jwt.encode(to_encode, _get_secret_key(), algorithm=settings.ALGORITHM)
    return encoded_jwt

# ========== DEBUG/HELPER FUNCTIONS ==========
def decode_token_for_debug(token: str) -> dict:
    """Decode token for debugging purposes (no validation)"""
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        payload = jwt.decode(token, _get_secret_key(), algorithms=[settings.ALGORITHM])
        return {
            "success": True,
            "payload": payload,
            "user_id": payload.get("user_id"),
            "phone": payload.get("sub"),
            "type": payload.get("type"),
            "expires": datetime.fromtimestamp(payload.get("exp")) if payload.get("exp") else None
        }
    except JWTError as e:
        return {
            "success": False,
            "error": str(e),
            "token": token[:50] + "..." if len(token) > 50 else token
        }

def validate_token_for_frontend(token: str) -> dict:
    """Validate token and return user info for frontend"""
    try:
        payload = verify_token(token)
        user_identifier = payload.get("sub")
        
        # Get user from database
        from app.db.session import SessionLocal
        db = SessionLocal()
        
        try:
            if user_identifier and "@" in user_identifier:
                user = crud.user.get_user_by_email(db, email=user_identifier)
            else:
                user = crud.user.get_user_by_phone(db, phone=user_identifier)
            if user:
                return {
                    "valid": True,
                    "user_id": user.id,
                    "phone": user.phone,
                    "full_name": user.full_name,
                    "email": user.email
                }
            else:
                return {
                    "valid": False,
                    "error": "User not found in database"
                }
        finally:
            db.close()
            
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }