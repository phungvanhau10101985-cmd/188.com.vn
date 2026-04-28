# backend/app/models/bank_account.py - Tài khoản ngân hàng (cài đặt trong quản trị)
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.db.base import Base


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, index=True)
    bank_name = Column(String(255), nullable=False)
    account_number = Column(String(50), nullable=False)
    account_holder = Column(String(255), nullable=False)
    # Mã NH cho VietQR/SePay (ICB, MBBank, VCB, …)
    bank_code = Column(String(32), nullable=True)
    # URL mẫu QR, ví dụ: https://qr.sepay.vn/img?acc={bank_acc}&bank={bank_id}&amount={amount}&des={des}&template=compact
    qr_template_url = Column(Text, nullable=True)
    branch = Column(String(255), nullable=True)
    note = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<BankAccount {self.bank_name} {self.account_number}>"
