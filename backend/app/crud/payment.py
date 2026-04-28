# backend/app/crud/payment.py
"""Thanh toán / cọc — dùng bởi orders API và webhook SePay."""
from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.order import Payment, PaymentMethod, PaymentStatus


def _payment_code() -> str:
    return "PAY" + secrets.token_hex(4).upper()


def create_payment(
    db: Session,
    *,
    order_id: int,
    amount: Decimal,
    payment_method: str,
    payment_type: str,
    bank_name: Optional[str] = None,
    account_number: Optional[str] = None,
    account_name: Optional[str] = None,
    transaction_code: Optional[str] = None,
    transfer_date: Optional[datetime] = None,
    payment_status: Optional[str] = None,
    payment_gateway_data: Optional[Dict[str, Any]] = None,
) -> Payment:
    pm = (
        payment_method
        if isinstance(payment_method, PaymentMethod)
        else PaymentMethod(payment_method)
    )
    st = PaymentStatus.PENDING
    if payment_status:
        st = (
            payment_status
            if isinstance(payment_status, PaymentStatus)
            else PaymentStatus(payment_status)
        )
    p = Payment(
        payment_code=_payment_code(),
        order_id=order_id,
        amount=amount,
        payment_method=pm,
        payment_type=payment_type,
        payment_status=st,
        bank_name=bank_name,
        account_number=account_number,
        account_name=account_name,
        transaction_code=transaction_code,
        transfer_date=transfer_date,
        payment_gateway_data=payment_gateway_data,
    )
    if st == PaymentStatus.PAID:
        p.confirmed_at = datetime.now()
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def confirm_payment(
    db: Session,
    *,
    payment_id: int,
    admin_id: int,
    is_confirmed: bool,
    note: Optional[str] = None,
) -> Optional[Payment]:
    p = db.query(Payment).filter(Payment.id == payment_id).first()
    if not p:
        return None
    if is_confirmed:
        p.payment_status = PaymentStatus.PAID
        p.confirmed_by = admin_id
        p.confirmed_at = datetime.now()
        p.confirmation_note = note
    else:
        p.payment_status = PaymentStatus.FAILED
        p.confirmation_note = note
    db.commit()
    db.refresh(p)
    return p


def get_order_payments(db: Session, *, order_id: int) -> List[Payment]:
    return db.query(Payment).filter(Payment.order_id == order_id).order_by(Payment.id.desc()).all()


def find_payment_by_sepay_id(db: Session, sepay_id: str) -> Optional[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.transaction_code == sepay_id, Payment.payment_type == "deposit_sepay")
        .first()
    )
