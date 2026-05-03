# backend/app/crud/admin.py
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from app.models.admin import AdminUser, AdminRole
from app.schemas.admin import AdminCreate, AdminUpdate

# Import security bên trong hàm để tránh import vòng: crud.admin -> security -> crud

class AdminCRUD:
    def get_admin(self, db: Session, admin_id: int) -> Optional[AdminUser]:
        return db.query(AdminUser).filter(AdminUser.id == admin_id).first()

    def get_admin_by_username(self, db: Session, username: str) -> Optional[AdminUser]:
        if not username or not username.strip():
            return None
        uname = username.strip()
        u = db.query(AdminUser).filter(AdminUser.username == uname).first()
        if u:
            return u
        return db.query(AdminUser).filter(AdminUser.username == uname.lower()).first()

    def get_admin_by_email(self, db: Session, email: str) -> Optional[AdminUser]:
        return db.query(AdminUser).filter(AdminUser.email == email).first()

    def authenticate_admin(self, db: Session, username: str, password: str) -> Optional[AdminUser]:
        from app.core.security import verify_password, get_password_hash
        if not username or not password:
            return None
        uname = username.strip()
        pwd = (password.strip() if isinstance(password, str) else password) or ""
        if not pwd:
            return None
        u = db.query(AdminUser).filter(AdminUser.username == uname).first()
        if not u:
            u = db.query(AdminUser).filter(AdminUser.username == uname.lower()).first()
        if not u:
            return None
        if not u.password_hash:
            return None
        if verify_password(pwd, u.password_hash):
            return u
        # Hash cũ có thể không đúng format (passlib/bcrypt cũ): thử cập nhật sang bcrypt mới
        stored = (u.password_hash or "").strip()
        if not stored.startswith("$2"):
            try:
                u.password_hash = get_password_hash(pwd)
                db.commit()
                db.refresh(u)
                return u
            except Exception:
                db.rollback()
        return None

    def create_admin(self, db: Session, data: AdminCreate) -> AdminUser:
        from app.core.security import get_password_hash
        hashed = get_password_hash(data.password)
        role_enum = getattr(AdminRole, data.role.upper(), AdminRole.ADMIN) if isinstance(data.role, str) else AdminRole.ADMIN
        u = AdminUser(
            username=data.username,
            email=data.email,
            password_hash=hashed,
            full_name=data.full_name,
            phone=data.phone,
            role=role_enum,
            linked_user_id=data.linked_user_id,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u

    def update_admin(self, db: Session, admin_id: int, data: AdminUpdate) -> Optional[AdminUser]:
        u = self.get_admin(db, admin_id)
        if not u:
            return None
        d = data.model_dump(exclude_unset=True)
        if "role" in d and d["role"] is not None:
            d["role"] = getattr(AdminRole, str(d["role"]).upper(), AdminRole.ADMIN)
        for k, v in d.items():
            if hasattr(u, k):
                setattr(u, k, v)
        db.commit()
        db.refresh(u)
        return u

    def delete_admin(self, db: Session, admin_id: int) -> bool:
        u = self.get_admin(db, admin_id)
        if not u:
            return False
        db.delete(u)
        db.commit()
        return True

    def get_admins(self, db: Session, skip: int = 0, limit: int = 100) -> List[AdminUser]:
        return db.query(AdminUser).offset(skip).limit(limit).all()

_admin_crud = AdminCRUD()

def get_admin(db: Session, admin_id: int) -> Optional[AdminUser]:
    return _admin_crud.get_admin(db, admin_id)

def get_admin_by_username(db: Session, username: str) -> Optional[AdminUser]:
    return _admin_crud.get_admin_by_username(db, username)

def get_admin_by_email(db: Session, email: str) -> Optional[AdminUser]:
    return _admin_crud.get_admin_by_email(db, email)

def create_admin(db: Session, data: AdminCreate) -> AdminUser:
    return _admin_crud.create_admin(db, data)

def update_admin(db: Session, admin_id: int, data: AdminUpdate) -> Optional[AdminUser]:
    return _admin_crud.update_admin(db, admin_id, data)

def delete_admin(db: Session, admin_id: int) -> bool:
    return _admin_crud.delete_admin(db, admin_id)

def get_admins(db: Session, skip: int = 0, limit: int = 100) -> List[AdminUser]:
    return _admin_crud.get_admins(db, skip, limit)

def verify_admin_password(db: Session, username: str, password: str) -> Optional[AdminUser]:
    return _admin_crud.authenticate_admin(db, username, password)

def update_admin_last_login(db: Session, admin_id: int) -> Optional[AdminUser]:
    u = _admin_crud.get_admin(db, admin_id)
    if u:
        u.last_login = datetime.now()
        db.commit()
        db.refresh(u)
    return u