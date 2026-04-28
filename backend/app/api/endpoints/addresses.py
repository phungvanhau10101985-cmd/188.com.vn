# backend/app/api/endpoints/addresses.py - Sổ địa chỉ API
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.core.security import get_current_user
from app import models, crud
from app.schemas.address import AddressCreate, AddressUpdate, AddressResponse

router = APIRouter()


@router.get("", response_model=List[AddressResponse], include_in_schema=False)
@router.get("/", response_model=List[AddressResponse])
def list_addresses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Danh sách địa chỉ của user."""
    return crud.address.get_addresses(db, current_user.id)


@router.post("", response_model=AddressResponse, include_in_schema=False)
@router.post("/", response_model=AddressResponse)
def create_address(
    data: AddressCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Thêm địa chỉ mới (và lưu vào sổ địa chỉ)."""
    return crud.address.create_address(db, current_user.id, data)


@router.get("/default", response_model=Optional[AddressResponse])
def get_default_address(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lấy địa chỉ mặc định."""
    addr = crud.address.get_default_address(db, current_user.id)
    return addr


@router.get("/{address_id}", response_model=AddressResponse)
def get_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Chi tiết một địa chỉ."""
    addr = crud.address.get_address(db, address_id, current_user.id)
    if not addr:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa chỉ")
    return addr


@router.put("/{address_id}", response_model=AddressResponse)
def update_address(
    address_id: int,
    data: AddressUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cập nhật địa chỉ."""
    addr = crud.address.update_address(db, address_id, current_user.id, data)
    if not addr:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa chỉ")
    return addr


@router.post("/{address_id}/set-default", response_model=AddressResponse)
def set_default_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Đặt địa chỉ làm mặc định."""
    addr = crud.address.set_default_address(db, address_id, current_user.id)
    if not addr:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa chỉ")
    return addr


@router.delete("/{address_id}", status_code=204)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Xóa địa chỉ."""
    ok = crud.address.delete_address(db, address_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa chỉ")
