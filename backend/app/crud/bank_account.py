# backend/app/crud/bank_account.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.bank_account import BankAccount
from app.schemas.bank_account import BankAccountCreate, BankAccountUpdate


def get_bank_accounts(db: Session, active_only: bool = True) -> List[BankAccount]:
    q = db.query(BankAccount)
    if active_only:
        q = q.filter(BankAccount.is_active == True)
    return q.order_by(BankAccount.sort_order, BankAccount.id).all()


def get_bank_account(db: Session, account_id: int) -> Optional[BankAccount]:
    return db.query(BankAccount).filter(BankAccount.id == account_id).first()


def create_bank_account(db: Session, data: BankAccountCreate) -> BankAccount:
    acc = BankAccount(**data.model_dump())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def update_bank_account(db: Session, account_id: int, data: BankAccountUpdate) -> Optional[BankAccount]:
    acc = get_bank_account(db, account_id)
    if not acc:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(acc, k, v)
    db.commit()
    db.refresh(acc)
    return acc


def delete_bank_account(db: Session, account_id: int) -> bool:
    acc = get_bank_account(db, account_id)
    if not acc:
        return False
    db.delete(acc)
    db.commit()
    return True
