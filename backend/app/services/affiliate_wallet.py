from __future__ import annotations

import hashlib
import json
import logging
import secrets
import string
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.affiliate import (
    AffiliateApplication,
    AffiliateBankAccountOtp,
    AffiliateCommission,
    AffiliateProfile,
    AffiliateSettings,
    UserBankAccount,
    UserWallet,
    WalletTransaction,
    WalletWithdrawal,
)
from app.models.order import Order, OrderStatus
from app.services.email_service import send_bank_account_otp_email

logger = logging.getLogger(__name__)

COMMISSION_STATUS_PENDING = "pending"
COMMISSION_STATUS_CONFIRMED = "confirmed"
COMMISSION_STATUS_CANCELLED = "cancelled"

WITHDRAWAL_STATUS_PENDING = "pending"
WITHDRAWAL_STATUS_APPROVED = "approved"
WITHDRAWAL_STATUS_REJECTED = "rejected"

APPLICATION_STATUS_PENDING = "pending"
APPLICATION_STATUS_APPROVED = "approved"
APPLICATION_STATUS_REJECTED = "rejected"

BANK_ACCOUNT_OTP_EXPIRE_MINUTES = 10
BANK_ACCOUNT_OTP_LENGTH = 6


def _dec(v) -> Decimal:
    if v is None:
        return Decimal("0")
    return Decimal(str(v)).quantize(Decimal("0.01"))


def _hash_value(value: str) -> str:
    pepper = (settings.SECRET_KEY or "dev").encode("utf-8")
    return hashlib.sha256(pepper + b":" + value.strip().encode("utf-8")).hexdigest()


def _bank_payload_hash(bank_name: str, bank_account: str, account_holder: str) -> str:
    payload = "|".join(
        [
            (bank_name or "").strip().lower(),
            (bank_account or "").strip().replace(" ", ""),
            (account_holder or "").strip().lower(),
        ]
    )
    return _hash_value(payload)


def _clean_social_links(links: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in links or []:
        link = (raw or "").strip()
        if not link:
            continue
        if len(link) > 500:
            raise ValueError("Link mạng xã hội quá dài.")
        if not (link.startswith("http://") or link.startswith("https://")):
            raise ValueError("Link mạng xã hội phải bắt đầu bằng http:// hoặc https://.")
        if link not in cleaned:
            cleaned.append(link)
    if not cleaned:
        raise ValueError("Vui lòng nhập ít nhất một link mạng xã hội cá nhân.")
    return cleaned[:10]


def _application_to_dict(row: Optional[AffiliateApplication]) -> Optional[dict]:
    if not row:
        return None
    try:
        social_links = json.loads(row.social_links or "[]")
        if not isinstance(social_links, list):
            social_links = []
    except Exception:
        social_links = []
    return {
        "id": row.id,
        "user_id": row.user_id,
        "status": row.status,
        "social_links": [str(x) for x in social_links],
        "note": row.note,
        "admin_note": row.admin_note,
        "reviewed_by": row.reviewed_by,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "updated_at": row.updated_at,
    }


def get_affiliate_application(db: Session, user_id: int) -> Optional[AffiliateApplication]:
    return db.query(AffiliateApplication).filter(AffiliateApplication.user_id == user_id).first()


def is_user_approved_affiliate(db: Session, user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    row = get_affiliate_application(db, int(user_id))
    return bool(row and row.status == APPLICATION_STATUS_APPROVED)


def submit_affiliate_application(
    db: Session,
    *,
    user_id: int,
    social_links: list[str],
    note: Optional[str] = None,
) -> AffiliateApplication:
    links = _clean_social_links(social_links)
    row = get_affiliate_application(db, user_id)
    if not row:
        row = AffiliateApplication(user_id=user_id)
        db.add(row)
    elif row.status == APPLICATION_STATUS_APPROVED:
        raise ValueError("Tài khoản đã được phê duyệt làm affiliate.")
    row.status = APPLICATION_STATUS_PENDING
    row.social_links = json.dumps(links, ensure_ascii=False)
    row.note = (note or "").strip() or None
    row.admin_note = None
    row.reviewed_by = None
    row.reviewed_at = None
    row.submitted_at = datetime.utcnow()
    get_or_create_profile(db, user_id)
    db.flush()
    return row


def list_affiliate_applications(db: Session, status: Optional[str] = None, skip: int = 0, limit: int = 100) -> list[dict]:
    q = db.query(AffiliateApplication).order_by(AffiliateApplication.submitted_at.desc())
    if status:
        q = q.filter(AffiliateApplication.status == status.strip())
    return [_application_to_dict(row) for row in q.offset(skip).limit(limit).all()]


def approve_affiliate_application(db: Session, application_id: int, admin_id: int, admin_note: Optional[str] = None) -> AffiliateApplication:
    row = db.query(AffiliateApplication).filter(AffiliateApplication.id == application_id).first()
    if not row:
        raise ValueError("Không tìm thấy hồ sơ đăng ký affiliate.")
    row.status = APPLICATION_STATUS_APPROVED
    row.admin_note = (admin_note or "").strip() or None
    row.reviewed_by = admin_id
    row.reviewed_at = datetime.utcnow()
    get_or_create_profile(db, row.user_id)
    db.flush()
    return row


def reject_affiliate_application(db: Session, application_id: int, admin_id: int, admin_note: Optional[str] = None) -> AffiliateApplication:
    row = db.query(AffiliateApplication).filter(AffiliateApplication.id == application_id).first()
    if not row:
        raise ValueError("Không tìm thấy hồ sơ đăng ký affiliate.")
    row.status = APPLICATION_STATUS_REJECTED
    row.admin_note = (admin_note or "").strip() or None
    row.reviewed_by = admin_id
    row.reviewed_at = datetime.utcnow()
    db.flush()
    return row


def _default_commission_percent() -> Decimal:
    return _dec(getattr(settings, "AFFILIATE_COMMISSION_PERCENT", 10))


def _default_min_withdrawal_amount() -> Decimal:
    return _dec(getattr(settings, "AFFILIATE_MIN_WITHDRAWAL", 100000))


def _default_ref_cookie_days() -> int:
    raw = getattr(settings, "AFFILIATE_REF_COOKIE_DAYS", 30)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 30


def get_or_create_settings(db: Session) -> AffiliateSettings:
    row = db.query(AffiliateSettings).filter(AffiliateSettings.id == 1).first()
    if row:
        return row
    row = AffiliateSettings(
        id=1,
        enabled=True,
        commission_percent=_default_commission_percent(),
        min_withdrawal=_default_min_withdrawal_amount(),
        ref_cookie_days=_default_ref_cookie_days(),
        commission_policy=None,
    )
    db.add(row)
    db.flush()
    return row


def update_settings(
    db: Session,
    *,
    enabled: bool,
    commission_percent_value: Decimal,
    min_withdrawal_value: Decimal,
    ref_cookie_days: int,
    commission_policy: Optional[str],
    admin_id: Optional[int],
) -> AffiliateSettings:
    row = get_or_create_settings(db)
    row.enabled = bool(enabled)
    row.commission_percent = _dec(commission_percent_value)
    row.min_withdrawal = _dec(min_withdrawal_value)
    row.ref_cookie_days = max(1, int(ref_cookie_days))
    row.commission_policy = (commission_policy or "").strip() or None
    row.updated_by = admin_id
    db.flush()
    return row


def affiliate_enabled(db: Session) -> bool:
    return bool(get_or_create_settings(db).enabled)


def commission_percent(db: Optional[Session] = None) -> Decimal:
    if db is None:
        return _default_commission_percent()
    return _dec(get_or_create_settings(db).commission_percent)


def min_withdrawal_amount(db: Optional[Session] = None) -> Decimal:
    if db is None:
        return _default_min_withdrawal_amount()
    return _dec(get_or_create_settings(db).min_withdrawal)


def _generate_referral_code(db: Session) -> str:
    for _ in range(20):
        code = secrets.token_urlsafe(5).upper().replace("-", "").replace("_", "")[:8]
        exists = db.query(AffiliateProfile.id).filter(AffiliateProfile.referral_code == code).first()
        if not exists:
            return code
    return f"U{secrets.randbelow(99999999):08d}"


def get_or_create_profile(db: Session, user_id: int) -> AffiliateProfile:
    profile = db.query(AffiliateProfile).filter(AffiliateProfile.user_id == user_id).first()
    if profile:
        return profile
    profile = AffiliateProfile(user_id=user_id, referral_code=_generate_referral_code(db))
    db.add(profile)
    db.flush()
    get_or_create_wallet(db, user_id)
    return profile


def get_or_create_wallet(db: Session, user_id: int) -> UserWallet:
    wallet = db.query(UserWallet).filter(UserWallet.user_id == user_id).first()
    if wallet:
        return wallet
    wallet = UserWallet(user_id=user_id, balance=Decimal("0"), pending_balance=Decimal("0"))
    db.add(wallet)
    db.flush()
    return wallet


def _append_tx(
    db: Session,
    *,
    user_id: int,
    tx_type: str,
    amount: Decimal,
    wallet: UserWallet,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    description: Optional[str] = None,
) -> WalletTransaction:
    tx = WalletTransaction(
        user_id=user_id,
        tx_type=tx_type,
        amount=amount,
        balance_after=wallet.balance,
        pending_after=wallet.pending_balance,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )
    db.add(tx)
    return tx


def user_has_completed_orders(db: Session, user_id: int) -> bool:
    done = {OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value}
    row = (
        db.query(Order.id)
        .filter(Order.user_id == user_id)
        .filter(Order.status.in_(list(done)))
        .first()
    )
    return row is not None


def attribute_referral(db: Session, user_id: int, referral_code: str) -> AffiliateProfile:
    code = (referral_code or "").strip().upper()
    if not code:
        raise ValueError("Mã giới thiệu không hợp lệ.")
    if not affiliate_enabled(db):
        raise ValueError("Chương trình affiliate đang tắt.")

    profile = get_or_create_profile(db, user_id)
    if profile.referred_by_user_id:
        return profile
    if user_has_completed_orders(db, user_id):
        return profile

    referrer_profile = db.query(AffiliateProfile).filter(AffiliateProfile.referral_code == code).first()
    if not referrer_profile or referrer_profile.user_id == user_id:
        raise ValueError("Mã giới thiệu không hợp lệ.")
    if not is_user_approved_affiliate(db, referrer_profile.user_id):
        raise ValueError("Người giới thiệu chưa được phê duyệt affiliate.")

    profile.referred_by_user_id = referrer_profile.user_id
    profile.referred_at = datetime.utcnow()
    db.flush()
    return profile


def commission_base_from_order(order: Order) -> Decimal:
    subtotal = _dec(order.subtotal)
    discount = _dec(order.discount_amount)
    wallet_used = _dec(getattr(order, "wallet_amount_used", None))
    return max(Decimal("0"), subtotal - discount - wallet_used)


def create_pending_commission_for_order(db: Session, order: Order) -> Optional[AffiliateCommission]:
    if not affiliate_enabled(db):
        return None
    if not order.user_id:
        return None

    buyer_profile = db.query(AffiliateProfile).filter(AffiliateProfile.user_id == order.user_id).first()
    if not buyer_profile or not buyer_profile.referred_by_user_id:
        return None
    if buyer_profile.referred_by_user_id == order.user_id:
        return None
    if not is_user_approved_affiliate(db, buyer_profile.referred_by_user_id):
        return None

    exists = db.query(AffiliateCommission.id).filter(AffiliateCommission.order_id == order.id).first()
    if exists:
        return None

    base = commission_base_from_order(order)
    if base <= 0:
        return None

    pct = commission_percent(db)
    amount = (base * pct / Decimal("100")).quantize(Decimal("0.01"))
    if amount <= 0:
        return None

    commission = AffiliateCommission(
        referrer_user_id=buyer_profile.referred_by_user_id,
        buyer_user_id=order.user_id,
        order_id=order.id,
        order_base_amount=base,
        commission_percent=pct,
        commission_amount=amount,
        status=COMMISSION_STATUS_PENDING,
    )
    db.add(commission)
    db.flush()

    wallet = get_or_create_wallet(db, commission.referrer_user_id)
    wallet.pending_balance = _dec(wallet.pending_balance) + amount
    _append_tx(
        db,
        user_id=commission.referrer_user_id,
        tx_type="commission_pending",
        amount=amount,
        wallet=wallet,
        reference_type="commission",
        reference_id=commission.id,
        description=f"Hoa hồng chờ xác nhận đơn #{order.order_code}",
    )
    return commission


def grant_deposit_commission_for_order(db: Session, order: Order) -> Optional[AffiliateCommission]:
    """Cộng hoa hồng vào ví ngay khi đơn đã được xác nhận đặt cọc."""
    if not affiliate_enabled(db):
        return None
    if not order.user_id:
        return None

    existing = db.query(AffiliateCommission).filter(AffiliateCommission.order_id == order.id).first()
    if existing:
        if existing.status == COMMISSION_STATUS_PENDING:
            confirm_commission_for_order(db, order.id)
            db.flush()
            db.refresh(existing)
        return existing if existing.status == COMMISSION_STATUS_CONFIRMED else None

    buyer_profile = db.query(AffiliateProfile).filter(AffiliateProfile.user_id == order.user_id).first()
    referrer_user_id = getattr(order, "referrer_user_id", None) or (
        buyer_profile.referred_by_user_id if buyer_profile else None
    )
    if not referrer_user_id or referrer_user_id == order.user_id:
        return None
    if not is_user_approved_affiliate(db, referrer_user_id):
        return None

    base = commission_base_from_order(order)
    if base <= 0:
        return None

    pct = commission_percent(db)
    amount = (base * pct / Decimal("100")).quantize(Decimal("0.01"))
    if amount <= 0:
        return None

    commission = AffiliateCommission(
        referrer_user_id=referrer_user_id,
        buyer_user_id=order.user_id,
        order_id=order.id,
        order_base_amount=base,
        commission_percent=pct,
        commission_amount=amount,
        status=COMMISSION_STATUS_CONFIRMED,
        confirmed_at=datetime.utcnow(),
    )
    db.add(commission)
    db.flush()

    wallet = get_or_create_wallet(db, referrer_user_id)
    wallet.balance = _dec(wallet.balance) + amount
    _append_tx(
        db,
        user_id=referrer_user_id,
        tx_type="commission_credit",
        amount=amount,
        wallet=wallet,
        reference_type="commission",
        reference_id=commission.id,
        description=f"Hoa hồng đặt cọc đơn #{order.order_code}",
    )
    return commission


def confirm_commission_for_order(db: Session, order_id: int) -> None:
    commission = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.order_id == order_id)
        .filter(AffiliateCommission.status == COMMISSION_STATUS_PENDING)
        .first()
    )
    if not commission:
        return

    wallet = get_or_create_wallet(db, commission.referrer_user_id)
    amount = _dec(commission.commission_amount)
    wallet.pending_balance = max(Decimal("0"), _dec(wallet.pending_balance) - amount)
    wallet.balance = _dec(wallet.balance) + amount
    commission.status = COMMISSION_STATUS_CONFIRMED
    commission.confirmed_at = datetime.utcnow()
    _append_tx(
        db,
        user_id=commission.referrer_user_id,
        tx_type="commission_credit",
        amount=amount,
        wallet=wallet,
        reference_type="commission",
        reference_id=commission.id,
        description=f"Hoa hồng đã duyệt đơn #{order_id}",
    )


def cancel_commission_for_order(db: Session, order_id: int) -> None:
    commission = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.order_id == order_id)
        .filter(AffiliateCommission.status.in_([COMMISSION_STATUS_PENDING, COMMISSION_STATUS_CONFIRMED]))
        .first()
    )
    if not commission:
        return

    wallet = get_or_create_wallet(db, commission.referrer_user_id)
    amount = _dec(commission.commission_amount)
    if commission.status == COMMISSION_STATUS_PENDING:
        wallet.pending_balance = max(Decimal("0"), _dec(wallet.pending_balance) - amount)
        tx_type = "commission_cancel_pending"
    else:
        # Cho phép âm ví để clawback đúng cả khi CTV đã dùng/rút hoa hồng trước đó.
        wallet.balance = _dec(wallet.balance) - amount
        tx_type = "commission_cancel"
    commission.status = COMMISSION_STATUS_CANCELLED
    _append_tx(
        db,
        user_id=commission.referrer_user_id,
        tx_type=tx_type,
        amount=-amount,
        wallet=wallet,
        reference_type="commission",
        reference_id=commission.id,
        description=f"Hủy hoa hồng đơn #{order_id}",
    )


def apply_wallet_to_order(db: Session, user_id: int, order: Order, requested_amount: Decimal) -> Decimal:
    requested = _dec(requested_amount)
    if requested <= 0:
        return Decimal("0")

    wallet = get_or_create_wallet(db, user_id)
    available = _dec(wallet.balance)
    order_total = _dec(order.total_amount)
    use_amount = min(requested, available, order_total)
    if use_amount <= 0:
        return Decimal("0")

    old_deposit = _dec(order.deposit_amount)
    wallet.balance = available - use_amount
    order.wallet_amount_used = use_amount
    order.total_amount = order_total - use_amount

    new_total = _dec(order.total_amount)
    if old_deposit > 0 and order_total > 0:
        order.deposit_amount = (old_deposit * new_total / order_total).quantize(Decimal("0.01"))
        order.remaining_amount = max(Decimal("0"), new_total - _dec(order.deposit_amount))
    elif old_deposit > 0:
        order.deposit_amount = min(old_deposit, new_total)
        order.remaining_amount = max(Decimal("0"), new_total - _dec(order.deposit_amount))

    if new_total == 0 and not order.requires_deposit:
        order.status = OrderStatus.CONFIRMED

    _append_tx(
        db,
        user_id=user_id,
        tx_type="order_payment",
        amount=-use_amount,
        wallet=wallet,
        reference_type="order",
        reference_id=order.id,
        description=f"Thanh toán đơn #{order.order_code} bằng ví",
    )
    return use_amount


def refund_wallet_for_order(db: Session, order: Order) -> None:
    used = _dec(getattr(order, "wallet_amount_used", None))
    if used <= 0 or not order.user_id:
        return
    wallet = get_or_create_wallet(db, order.user_id)
    wallet.balance = _dec(wallet.balance) + used
    order.wallet_amount_used = Decimal("0")
    _append_tx(
        db,
        user_id=order.user_id,
        tx_type="order_refund",
        amount=used,
        wallet=wallet,
        reference_type="order",
        reference_id=order.id,
        description=f"Hoàn ví đơn hủy #{order.order_code}",
    )


def handle_order_status_change(db: Session, order: Order, old_status: Optional[str], new_status: str) -> None:
    old_val = old_status.value if hasattr(old_status, "value") else (old_status or "")
    new_val = new_status.value if hasattr(new_status, "value") else new_status
    if old_val == new_val:
        return

    if new_val == OrderStatus.CANCELLED.value:
        cancel_commission_for_order(db, order.id)
        refund_wallet_for_order(db, order)
        return

    if new_val in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
        confirm_commission_for_order(db, order.id)


def handle_order_payment_status_change(db: Session, order: Order, new_payment_status: str) -> None:
    status_val = new_payment_status.value if hasattr(new_payment_status, "value") else new_payment_status
    if status_val == "refunded":
        cancel_commission_for_order(db, order.id)
        refund_wallet_for_order(db, order)


def save_bank_account(db: Session, user_id: int, bank_name: str, bank_account: str, account_holder: str) -> UserBankAccount:
    row = db.query(UserBankAccount).filter(UserBankAccount.user_id == user_id).first()
    if not row:
        row = UserBankAccount(user_id=user_id)
        db.add(row)
    row.bank_name = bank_name.strip()
    row.bank_account = bank_account.strip()
    row.account_holder = account_holder.strip()
    db.flush()
    return row


def request_bank_account_otp(
    db: Session,
    *,
    user_id: int,
    email: Optional[str],
    bank_name: str,
    bank_account: str,
    account_holder: str,
) -> dict:
    if not is_user_approved_affiliate(db, user_id):
        raise ValueError("Tài khoản chưa được phê duyệt làm affiliate.")
    email_key = (email or "").strip().lower()
    if not email_key or "@" not in email_key:
        raise ValueError("Tài khoản cần có email để nhận OTP xác minh ngân hàng.")
    if not settings.is_smtp_configured():
        raise ValueError("Máy chủ chưa cấu hình email SMTP để gửi OTP.")

    code = "".join(secrets.choice(string.digits) for _ in range(BANK_ACCOUNT_OTP_LENGTH))
    payload_hash = _bank_payload_hash(bank_name, bank_account, account_holder)
    now = datetime.utcnow()
    expires_at = now.replace(microsecond=0) + timedelta(minutes=BANK_ACCOUNT_OTP_EXPIRE_MINUTES)

    db.query(AffiliateBankAccountOtp).filter(
        AffiliateBankAccountOtp.user_id == user_id,
        AffiliateBankAccountOtp.consumed_at.is_(None),
    ).delete(synchronize_session=False)
    challenge = AffiliateBankAccountOtp(
        user_id=user_id,
        email=email_key,
        otp_hash=_hash_value(code),
        payload_hash=payload_hash,
        expires_at=expires_at,
    )
    db.add(challenge)
    db.flush()
    send_bank_account_otp_email(email_key, code, BANK_ACCOUNT_OTP_EXPIRE_MINUTES)
    return {
        "ok": True,
        "email": email_key,
        "expires_in_minutes": BANK_ACCOUNT_OTP_EXPIRE_MINUTES,
        "message": "Đã gửi mã OTP xác minh tài khoản ngân hàng.",
    }


def save_bank_account_with_otp(
    db: Session,
    *,
    user_id: int,
    bank_name: str,
    bank_account: str,
    account_holder: str,
    otp: str,
) -> UserBankAccount:
    code = (otp or "").strip()
    if not code:
        raise ValueError("Vui lòng nhập mã OTP.")
    now = datetime.utcnow()
    payload_hash = _bank_payload_hash(bank_name, bank_account, account_holder)
    row = (
        db.query(AffiliateBankAccountOtp)
        .filter(
            AffiliateBankAccountOtp.user_id == user_id,
            AffiliateBankAccountOtp.payload_hash == payload_hash,
            AffiliateBankAccountOtp.consumed_at.is_(None),
            AffiliateBankAccountOtp.expires_at > now,
        )
        .order_by(AffiliateBankAccountOtp.id.desc())
        .first()
    )
    if not row or row.otp_hash != _hash_value(code):
        raise ValueError("Mã OTP sai, hết hạn hoặc không khớp thông tin ngân hàng.")

    row.consumed_at = now
    return save_bank_account(db, user_id, bank_name, bank_account, account_holder)


def request_withdrawal(db: Session, user_id: int, amount: Decimal) -> WalletWithdrawal:
    if not is_user_approved_affiliate(db, user_id):
        raise ValueError("Tài khoản chưa được phê duyệt làm affiliate.")
    amt = _dec(amount)
    minimum = min_withdrawal_amount(db)
    if amt < minimum:
        raise ValueError(f"Số tiền rút tối thiểu là {minimum:,.0f} đ.")

    bank = db.query(UserBankAccount).filter(UserBankAccount.user_id == user_id).first()
    if not bank:
        raise ValueError("Vui lòng cập nhật tài khoản ngân hàng trước khi rút tiền.")

    wallet = get_or_create_wallet(db, user_id)
    if _dec(wallet.balance) < amt:
        raise ValueError("Số dư ví không đủ.")

    wallet.balance = _dec(wallet.balance) - amt
    withdrawal = WalletWithdrawal(
        user_id=user_id,
        amount=amt,
        bank_name=bank.bank_name,
        bank_account=bank.bank_account,
        account_holder=bank.account_holder,
        status=WITHDRAWAL_STATUS_PENDING,
    )
    db.add(withdrawal)
    db.flush()
    _append_tx(
        db,
        user_id=user_id,
        tx_type="withdrawal_hold",
        amount=-amt,
        wallet=wallet,
        reference_type="withdrawal",
        reference_id=withdrawal.id,
        description="Yêu cầu rút tiền — đang chờ duyệt",
    )
    return withdrawal


def approve_withdrawal(db: Session, withdrawal_id: int, admin_id: int) -> WalletWithdrawal:
    row = db.query(WalletWithdrawal).filter(WalletWithdrawal.id == withdrawal_id).first()
    if not row:
        raise ValueError("Không tìm thấy yêu cầu rút tiền.")
    if row.status != WITHDRAWAL_STATUS_PENDING:
        raise ValueError("Yêu cầu đã được xử lý.")
    row.status = WITHDRAWAL_STATUS_APPROVED
    row.processed_by = admin_id
    row.processed_at = datetime.utcnow()
    wallet = get_or_create_wallet(db, row.user_id)
    _append_tx(
        db,
        user_id=row.user_id,
        tx_type="withdrawal_paid",
        amount=Decimal("0"),
        wallet=wallet,
        reference_type="withdrawal",
        reference_id=row.id,
        description=f"Đã chuyển khoản rút {row.amount:,.0f} đ",
    )
    return row


def reject_withdrawal(db: Session, withdrawal_id: int, admin_id: int, admin_note: Optional[str] = None) -> WalletWithdrawal:
    row = db.query(WalletWithdrawal).filter(WalletWithdrawal.id == withdrawal_id).first()
    if not row:
        raise ValueError("Không tìm thấy yêu cầu rút tiền.")
    if row.status != WITHDRAWAL_STATUS_PENDING:
        raise ValueError("Yêu cầu đã được xử lý.")

    wallet = get_or_create_wallet(db, row.user_id)
    amt = _dec(row.amount)
    wallet.balance = _dec(wallet.balance) + amt
    row.status = WITHDRAWAL_STATUS_REJECTED
    row.admin_note = (admin_note or "").strip() or None
    row.processed_by = admin_id
    row.processed_at = datetime.utcnow()
    _append_tx(
        db,
        user_id=row.user_id,
        tx_type="withdrawal_rejected",
        amount=amt,
        wallet=wallet,
        reference_type="withdrawal",
        reference_id=row.id,
        description=row.admin_note or "Yêu cầu rút tiền bị từ chối — hoàn vào ví",
    )
    return row


def build_me_payload(db: Session, user_id: int) -> dict:
    profile = get_or_create_profile(db, user_id)
    wallet = get_or_create_wallet(db, user_id)
    affiliate_settings = get_or_create_settings(db)
    application = get_affiliate_application(db, user_id)
    application_status = application.status if application else "not_applied"
    is_approved = application_status == APPLICATION_STATUS_APPROVED
    base_url = (settings.FRONTEND_BASE_URL or "").rstrip("/")

    confirmed = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
        .filter(AffiliateCommission.referrer_user_id == user_id)
        .filter(AffiliateCommission.status == COMMISSION_STATUS_CONFIRMED)
        .scalar()
    )
    pending = (
        db.query(func.coalesce(func.sum(AffiliateCommission.commission_amount), 0))
        .filter(AffiliateCommission.referrer_user_id == user_id)
        .filter(AffiliateCommission.status == COMMISSION_STATUS_PENDING)
        .scalar()
    )
    referred_orders = (
        db.query(func.count(AffiliateCommission.id))
        .filter(AffiliateCommission.referrer_user_id == user_id)
        .scalar()
    ) or 0

    return {
        "referral_code": profile.referral_code,
        "referral_link": f"{base_url}/?ref={profile.referral_code}" if is_approved else "",
        "referred_by_user_id": profile.referred_by_user_id,
        "balance": _dec(wallet.balance),
        "pending_balance": _dec(wallet.pending_balance),
        "affiliate_enabled": bool(affiliate_settings.enabled),
        "commission_percent": float(commission_percent(db)),
        "min_withdrawal": min_withdrawal_amount(db),
        "ref_cookie_days": int(affiliate_settings.ref_cookie_days or _default_ref_cookie_days()),
        "commission_policy": affiliate_settings.commission_policy,
        "affiliate_status": application_status,
        "affiliate_application": _application_to_dict(application),
        "total_commissions_confirmed": _dec(confirmed),
        "total_commissions_pending": _dec(pending),
        "total_orders_referred": int(referred_orders),
    }
