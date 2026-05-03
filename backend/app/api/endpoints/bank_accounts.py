# backend/app/api/endpoints/bank_accounts.py - Tài khoản ngân hàng (public list + admin CRUD)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.core.security import require_module_permission
from app import models, crud, schemas

router = APIRouter()


@router.get("", response_model=List[schemas.BankAccountResponse], include_in_schema=False)
@router.get("/", response_model=List[schemas.BankAccountResponse])
def list_bank_accounts(
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    """Danh sách tài khoản ngân hàng (public - cho trang đặt cọc)."""
    return crud.bank_account.get_bank_accounts(db, active_only=active_only)


@router.get("/admin/all", response_model=List[schemas.BankAccountResponse])
def admin_list_all(
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Admin: Danh sách tất cả tài khoản."""
    return crud.bank_account.get_bank_accounts(db, active_only=False)


@router.post("/admin/", response_model=schemas.BankAccountResponse)
def admin_create(
    data: schemas.BankAccountCreate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Admin: Thêm tài khoản ngân hàng."""
    return crud.bank_account.create_bank_account(db, data)


@router.put("/admin/{account_id}", response_model=schemas.BankAccountResponse)
def admin_update(
    account_id: int,
    data: schemas.BankAccountUpdate,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Admin: Cập nhật tài khoản."""
    acc = crud.bank_account.update_bank_account(db, account_id, data)
    if not acc:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return acc


@router.delete("/admin/{account_id}", status_code=204)
def admin_delete(
    account_id: int,
    db: Session = Depends(get_db),
    current_admin: models.AdminUser = Depends(require_module_permission("bank_accounts")),
):
    """Admin: Xóa tài khoản."""
    ok = crud.bank_account.delete_bank_account(db, account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
