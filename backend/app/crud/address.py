# backend/app/crud/address.py - Sổ địa chỉ
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.address import UserAddress
from app.schemas.address import AddressCreate, AddressUpdate


def get_address(db: Session, address_id: int, user_id: int) -> Optional[UserAddress]:
    return db.query(UserAddress).filter(
        UserAddress.id == address_id,
        UserAddress.user_id == user_id
    ).first()


def get_addresses(db: Session, user_id: int) -> List[UserAddress]:
    return db.query(UserAddress).filter(UserAddress.user_id == user_id).order_by(
        UserAddress.is_default.desc(),
        UserAddress.created_at.desc()
    ).all()


def create_address(db: Session, user_id: int, data: AddressCreate) -> UserAddress:
    if data.is_default:
        db.query(UserAddress).filter(UserAddress.user_id == user_id).update({"is_default": False})
    addr = UserAddress(
        user_id=user_id,
        full_name=data.full_name,
        phone=data.phone,
        province=data.province,
        district=data.district,
        ward=data.ward,
        street_address=data.street_address,
        is_default=data.is_default,
    )
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return addr


def update_address(db: Session, address_id: int, user_id: int, data: AddressUpdate) -> Optional[UserAddress]:
    addr = get_address(db, address_id, user_id)
    if not addr:
        return None
    if data.is_default is True:
        db.query(UserAddress).filter(UserAddress.user_id == user_id).update({"is_default": False})
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(addr, k, v)
    db.commit()
    db.refresh(addr)
    return addr


def delete_address(db: Session, address_id: int, user_id: int) -> bool:
    addr = get_address(db, address_id, user_id)
    if not addr:
        return False
    db.delete(addr)
    db.commit()
    return True


def set_default_address(db: Session, address_id: int, user_id: int) -> Optional[UserAddress]:
    addr = get_address(db, address_id, user_id)
    if not addr:
        return None
    db.query(UserAddress).filter(UserAddress.user_id == user_id).update({"is_default": False})
    addr.is_default = True
    db.commit()
    db.refresh(addr)
    return addr


def get_default_address(db: Session, user_id: int) -> Optional[UserAddress]:
    return db.query(UserAddress).filter(
        UserAddress.user_id == user_id,
        UserAddress.is_default == True
    ).first()
