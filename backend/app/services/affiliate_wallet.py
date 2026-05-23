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

_COMMISSION_WITHDRAWABLE_ORDER_STATUSES = frozenset({
    OrderStatus.DELIVERED.value,
    OrderStatus.COMPLETED.value,
})

_COMMISSION_STATUS_LABELS = {
    "pending": "Chờ giao hàng",
    "confirmed": "Đã cộng — rút được",
    "cancelled": "Đã hủy",
    "awaiting_deposit": "Chờ khách đặt cọc",
}

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


def mask_buyer_label(order: Order) -> str:
    phone = "".join(c for c in (order.customer_phone or "") if c.isdigit())
    if len(phone) >= 4:
        return f"Khách ***{phone[-4:]}"
    code = (order.order_code or "").strip()
    return f"#{code}" if code else "Khách ẩn danh"


def _format_vnd_int(amount: Decimal) -> str:
    return f"{int(_dec(amount)):,}".replace(",", ".")


def _send_affiliate_notification(db: Session, user_id: int, title: str, content: str) -> None:
    try:
        from app.crud import notification as crud_notification
        from app.schemas.notification import NotificationCreate

        crud_notification.create_notification(
            db,
            NotificationCreate(user_id=user_id, title=title, content=content, type="affiliate"),
        )
    except Exception:
        logger.exception("affiliate notification failed user_id=%s title=%s", user_id, title)


def _run_affiliate_notify_task(task_name: str, order_id: int) -> None:
    from app.db.session import SessionLocal
    from sqlalchemy.orm import joinedload

    db = SessionLocal()
    try:
        order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
        if not order:
            return
        if task_name == "new_order":
            notify_referrer_new_order(db, order)
        elif task_name == "deposit":
            commission = (
                db.query(AffiliateCommission).filter(AffiliateCommission.order_id == order_id).first()
            )
            if commission:
                notify_referrer_deposit_commission(db, order, commission)
        elif task_name == "confirmed":
            commission = (
                db.query(AffiliateCommission)
                .filter(AffiliateCommission.order_id == order_id)
                .filter(AffiliateCommission.status == COMMISSION_STATUS_CONFIRMED)
                .first()
            )
            if commission:
                notify_referrer_commission_confirmed(db, order, commission)
    except Exception:
        logger.exception("affiliate notify task failed task=%s order_id=%s", task_name, order_id)
    finally:
        db.close()


def notify_referrer_new_order_task(order_id: int) -> None:
    _run_affiliate_notify_task("new_order", order_id)


def notify_referrer_deposit_commission_task(order_id: int) -> None:
    _run_affiliate_notify_task("deposit", order_id)


def notify_referrer_commission_confirmed_task(order_id: int) -> None:
    _run_affiliate_notify_task("confirmed", order_id)


def resolve_order_referrer_user_id(
    db: Session,
    *,
    user_id: Optional[int],
    referral_code: Optional[str] = None,
) -> Optional[int]:
    referrer_user_id: Optional[int] = None
    buyer_profile: Optional[AffiliateProfile] = None
    if user_id:
        buyer_profile = get_or_create_profile(db, user_id)
        referrer_user_id = buyer_profile.referred_by_user_id

    code = (referral_code or "").strip().upper()
    if code:
        ref_profile = db.query(AffiliateProfile).filter(AffiliateProfile.referral_code == code).first()
        if ref_profile and is_user_approved_affiliate(db, ref_profile.user_id):
            if not user_id or ref_profile.user_id != user_id:
                referrer_user_id = ref_profile.user_id
                if user_id and buyer_profile and not buyer_profile.referred_by_user_id:
                    try:
                        attribute_referral(db, user_id, code)
                    except ValueError:
                        pass
    return referrer_user_id


def notify_referrer_new_order(db: Session, order: Order) -> None:
    referrer_id = getattr(order, "referrer_user_id", None)
    if not referrer_id or not is_user_approved_affiliate(db, int(referrer_id)):
        return
    base = commission_base_from_order(order)
    pct = commission_percent(db)
    est = (base * pct / Decimal("100")).quantize(Decimal("0.01")) if base > 0 else Decimal("0")
    buyer = mask_buyer_label(order)
    code = order.order_code or str(order.id)
    if order.requires_deposit and _dec(order.deposit_amount) > 0:
        content = (
            f"{buyer} vừa đặt đơn {code} qua link của bạn. "
            f"Hoa hồng dự kiến {_format_vnd_int(est)}đ — hiển thị sau khi khách đặt cọc."
        )
    else:
        content = (
            f"{buyer} vừa đặt đơn {code} qua link của bạn. "
            f"Hoa hồng {_format_vnd_int(est)}đ đang chờ — rút được khi giao thành công."
        )
    _send_affiliate_notification(
        db,
        int(referrer_id),
        "Có đơn hàng từ link giới thiệu",
        content,
    )


def notify_referrer_deposit_commission(db: Session, order: Order, commission: AffiliateCommission) -> None:
    buyer = mask_buyer_label(order)
    code = order.order_code or str(order.id)
    amt = _dec(commission.commission_amount)
    _send_affiliate_notification(
        db,
        commission.referrer_user_id,
        "Khách đã đặt cọc — hoa hồng chờ giao hàng",
        (
            f"{buyer} · đơn {code}: hoa hồng {_format_vnd_int(amt)}đ đã ghi nhận. "
            "Bạn có thể rút sau khi đơn giao thành công."
        ),
    )


def notify_referrer_commission_confirmed(db: Session, order: Order, commission: AffiliateCommission) -> None:
    buyer = mask_buyer_label(order)
    code = order.order_code or str(order.id)
    amt = _dec(commission.commission_amount)
    _send_affiliate_notification(
        db,
        commission.referrer_user_id,
        "Hoa hồng đã có thể rút",
        (
            f"Đơn {code} ({buyer}) đã giao thành công. "
            f"Hoa hồng {_format_vnd_int(amt)}đ đã chuyển vào số dư khả dụng."
        ),
    )


def _order_status_value(order: Order | str) -> str:
    if isinstance(order, str):
        return order
    return getattr(order.status, "value", order.status) or ""


def _order_allows_commission_withdrawal(order_status: str) -> bool:
    return order_status in _COMMISSION_WITHDRAWABLE_ORDER_STATUSES


def _resolve_commission_display(
    comm: Optional[AffiliateCommission],
    order: Order,
) -> dict:
    st = _order_status_value(order)
    if comm:
        if comm.status == COMMISSION_STATUS_CANCELLED:
            return {
                "commission_status": "cancelled",
                "commission_status_label": _COMMISSION_STATUS_LABELS["cancelled"],
                "withdrawable": False,
                "commission_created_at": comm.created_at,
                "commission_confirmed_at": None,
            }
        if comm.status == COMMISSION_STATUS_CONFIRMED and _order_allows_commission_withdrawal(st):
            return {
                "commission_status": "confirmed",
                "commission_status_label": _COMMISSION_STATUS_LABELS["confirmed"],
                "withdrawable": True,
                "commission_created_at": comm.created_at,
                "commission_confirmed_at": comm.confirmed_at,
            }
        return {
            "commission_status": "pending",
            "commission_status_label": _COMMISSION_STATUS_LABELS["pending"],
            "withdrawable": False,
            "commission_created_at": comm.created_at,
            "commission_confirmed_at": None,
        }
    if st == "cancelled":
        return {
            "commission_status": "cancelled",
            "commission_status_label": _COMMISSION_STATUS_LABELS["cancelled"],
            "withdrawable": False,
            "commission_created_at": None,
            "commission_confirmed_at": None,
        }
    if order.requires_deposit and st == "waiting_deposit":
        return {
            "commission_status": "awaiting_deposit",
            "commission_status_label": _COMMISSION_STATUS_LABELS["awaiting_deposit"],
            "withdrawable": False,
            "commission_created_at": None,
            "commission_confirmed_at": None,
        }
    return {
        "commission_status": "pending",
        "commission_status_label": _COMMISSION_STATUS_LABELS["pending"],
        "withdrawable": False,
        "commission_created_at": order.created_at,
        "commission_confirmed_at": None,
    }


def _order_status_label(status_val: str) -> str:
    labels = {
        "pending": "Chờ xác nhận",
        "waiting_deposit": "Chờ đặt cọc",
        "deposit_paid": "Đã đặt cọc",
        "confirmed": "Đã xác nhận",
        "processing": "Đang xử lý",
        "shipping": "Đang giao",
        "delivered": "Đã giao",
        "completed": "Hoàn tất",
        "cancelled": "Đã hủy",
    }
    return labels.get(status_val, status_val)


def _product_summary(order: Order, max_len: int = 80) -> str:
    items = getattr(order, "items", None) or []
    if not items:
        return "—"
    names = [(getattr(i, "product_name", None) or "").strip() for i in items]
    names = [n for n in names if n]
    if not names:
        return "—"
    text = names[0]
    if len(items) > 1:
        text = f"{text} (+{len(items) - 1} SP)"
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def list_referred_orders_for_affiliate(
    db: Session,
    referrer_user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    from sqlalchemy.orm import joinedload

    if not is_user_approved_affiliate(db, referrer_user_id):
        return []

    orders = (
        db.query(Order)
        .options(joinedload(Order.items))
        .filter(Order.referrer_user_id == referrer_user_id)
        .order_by(Order.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    if not orders:
        return []

    order_ids = [o.id for o in orders]
    commissions = {
        c.order_id: c
        for c in db.query(AffiliateCommission).filter(AffiliateCommission.order_id.in_(order_ids)).all()
    }
    pct = commission_percent(db)

    rows: list[dict] = []
    for order in orders:
        st = getattr(order.status, "value", order.status) or ""
        comm = commissions.get(order.id)
        base = _dec(comm.order_base_amount) if comm else commission_base_from_order(order)
        comm_amt = _dec(comm.commission_amount) if comm else (
            (base * pct / Decimal("100")).quantize(Decimal("0.01")) if base > 0 else Decimal("0")
        )
        comm_pct = float(comm.commission_percent) if comm else float(pct)
        display = _resolve_commission_display(comm, order)

        rows.append(
            {
                "order_id": order.id,
                "order_code": order.order_code,
                "buyer_label": mask_buyer_label(order),
                "product_summary": _product_summary(order),
                "order_total": _dec(order.total_amount),
                "order_status": st,
                "order_status_label": _order_status_label(st),
                "commission_amount": comm_amt,
                "commission_percent": comm_pct,
                "commission_status": display["commission_status"],
                "commission_status_label": display["commission_status_label"],
                "withdrawable": display["withdrawable"],
                "order_created_at": order.created_at,
                "commission_created_at": display["commission_created_at"],
                "commission_confirmed_at": display["commission_confirmed_at"],
            }
        )
    return rows


def commission_base_from_order(order: Order) -> Decimal:
    subtotal = _dec(order.subtotal)
    discount = _dec(order.discount_amount)
    wallet_used = _dec(getattr(order, "wallet_amount_used", None))
    return max(Decimal("0"), subtotal - discount - wallet_used)


def create_pending_commission_for_order(db: Session, order: Order) -> Optional[AffiliateCommission]:
    if not affiliate_enabled(db):
        return None

    buyer_profile = (
        db.query(AffiliateProfile).filter(AffiliateProfile.user_id == order.user_id).first()
        if order.user_id
        else None
    )
    referrer_user_id = getattr(order, "referrer_user_id", None) or (
        buyer_profile.referred_by_user_id if buyer_profile else None
    )
    if not referrer_user_id:
        return None
    if order.user_id and referrer_user_id == order.user_id:
        return None
    if not is_user_approved_affiliate(db, int(referrer_user_id)):
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
        referrer_user_id=int(referrer_user_id),
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
        description=f"Hoa hồng chờ giao hàng đơn #{order.order_code}",
    )
    return commission


def record_referral_commission_on_deposit(db: Session, order: Order) -> Optional[AffiliateCommission]:
    """Ghi nhận hoa hồng pending khi khách đặt cọc — chỉ chuyển sang số dư rút được sau giao hàng."""
    if not affiliate_enabled(db):
        return None

    existing = db.query(AffiliateCommission).filter(AffiliateCommission.order_id == order.id).first()
    if existing:
        return None

    return create_pending_commission_for_order(db, order)


def grant_deposit_commission_for_order(db: Session, order: Order) -> Optional[AffiliateCommission]:
    """Backward-compatible alias — hoa hồng chỉ pending, không cộng balance ngay."""
    return record_referral_commission_on_deposit(db, order)


def confirm_commission_for_order(db: Session, order_id: int) -> bool:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return False
    if not _order_allows_commission_withdrawal(_order_status_value(order)):
        return False

    commission = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.order_id == order_id)
        .filter(AffiliateCommission.status == COMMISSION_STATUS_PENDING)
        .first()
    )
    if not commission:
        return False

    wallet = get_or_create_wallet(db, commission.referrer_user_id)
    amount = _dec(commission.commission_amount)
    wallet.pending_balance = max(Decimal("0"), _dec(wallet.pending_balance) - amount)
    wallet.balance = _dec(wallet.balance) + amount
    commission.status = COMMISSION_STATUS_CONFIRMED
    commission.confirmed_at = datetime.utcnow()
    order_code = order.order_code if order else str(order_id)
    _append_tx(
        db,
        user_id=commission.referrer_user_id,
        tx_type="commission_credit",
        amount=amount,
        wallet=wallet,
        reference_type="commission",
        reference_id=commission.id,
        description=f"Hoa hồng đã giao thành công đơn #{order_code}",
    )
    return True


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


def handle_order_status_change(db: Session, order: Order, old_status: Optional[str], new_status: str) -> bool:
    old_val = old_status.value if hasattr(old_status, "value") else (old_status or "")
    new_val = new_status.value if hasattr(new_status, "value") else new_status
    if old_val == new_val:
        return False

    if new_val == OrderStatus.CANCELLED.value:
        cancel_commission_for_order(db, order.id)
        refund_wallet_for_order(db, order)
        return False

    if new_val in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
        return confirm_commission_for_order(db, order.id)
    return False


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


_TX_TYPE_LABELS = {
    "commission_pending": "Hoa hồng chờ giao hàng",
    "commission_credit": "Chuyển sang có thể rút",
    "commission_cancel_pending": "Hủy hoa hồng chờ giao",
    "commission_cancel": "Thu hồi hoa hồng",
    "commission_revert_premature": "Điều chỉnh chờ giao hàng",
    "order_payment": "Thanh toán đơn bằng ví",
    "order_refund": "Hoàn ví đơn hủy",
    "withdrawal_hold": "Giữ tiền chờ rút",
    "withdrawal_paid": "Đã chuyển khoản rút",
    "withdrawal_rejected": "Hoàn tiền rút bị từ chối",
}

_TX_AFFECTS_BUCKET = {
    "commission_pending": "pending",
    "commission_credit": "both",
    "commission_cancel_pending": "pending",
    "commission_cancel": "withdrawable",
    "order_payment": "withdrawable",
    "order_refund": "withdrawable",
    "withdrawal_hold": "withdrawable",
    "withdrawal_paid": "withdrawable",
    "withdrawal_rejected": "withdrawable",
}


def list_wallet_transactions_for_user(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    from sqlalchemy.orm import joinedload

    txs = (
        db.query(WalletTransaction)
        .filter(WalletTransaction.user_id == user_id)
        .order_by(WalletTransaction.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    if not txs:
        return []

    commission_ids = [
        tx.reference_id for tx in txs if tx.reference_type == "commission" and tx.reference_id
    ]
    order_ids = [tx.reference_id for tx in txs if tx.reference_type == "order" and tx.reference_id]

    commission_order_map: dict[int, int] = {}
    if commission_ids:
        for comm in db.query(AffiliateCommission).filter(AffiliateCommission.id.in_(commission_ids)).all():
            commission_order_map[comm.id] = comm.order_id
            order_ids.append(comm.order_id)

    order_ids = list({oid for oid in order_ids if oid})
    orders_by_id: dict[int, Order] = {}
    if order_ids:
        for order in (
            db.query(Order)
            .options(joinedload(Order.items))
            .filter(Order.id.in_(order_ids))
            .all()
        ):
            orders_by_id[order.id] = order

    rows: list[dict] = []
    for tx in txs:
        order: Optional[Order] = None
        if tx.reference_type == "order" and tx.reference_id:
            order = orders_by_id.get(tx.reference_id)
        elif tx.reference_type == "commission" and tx.reference_id:
            order_id = commission_order_map.get(tx.reference_id)
            if order_id:
                order = orders_by_id.get(order_id)

        order_status = None
        order_status_label = None
        product_summary = None
        order_code = None
        if order:
            order_status = getattr(order.status, "value", order.status) or ""
            order_status_label = _order_status_label(order_status)
            product_summary = _product_summary(order)
            order_code = order.order_code

        rows.append(
            {
                "id": tx.id,
                "tx_type": tx.tx_type,
                "tx_type_label": _TX_TYPE_LABELS.get(tx.tx_type, tx.tx_type),
                "amount": _dec(tx.amount),
                "balance_after": _dec(tx.balance_after),
                "pending_after": _dec(tx.pending_after),
                "description": tx.description,
                "reference_type": tx.reference_type,
                "reference_id": tx.reference_id,
                "order_code": order_code,
                "order_status": order_status,
                "order_status_label": order_status_label,
                "product_summary": product_summary,
                "affects_bucket": _TX_AFFECTS_BUCKET.get(tx.tx_type),
                "created_at": tx.created_at,
            }
        )
    return rows


def repair_premature_commission_confirmations(db: Session) -> int:
    """Hoàn tác hoa hồng bị xác nhận sớm (legacy: cộng ngay khi đặt cọc)."""
    commissions = (
        db.query(AffiliateCommission)
        .filter(AffiliateCommission.status == COMMISSION_STATUS_CONFIRMED)
        .all()
    )
    if not commissions:
        return 0

    order_ids = [c.order_id for c in commissions]
    orders_by_id = {
        o.id: o for o in db.query(Order).filter(Order.id.in_(order_ids)).all()
    }

    fixed = 0
    for commission in commissions:
        order = orders_by_id.get(commission.order_id)
        if not order:
            continue
        if _order_allows_commission_withdrawal(_order_status_value(order)):
            continue

        wallet = get_or_create_wallet(db, commission.referrer_user_id)
        amount = _dec(commission.commission_amount)
        wallet.balance = _dec(wallet.balance) - amount
        wallet.pending_balance = _dec(wallet.pending_balance) + amount
        commission.status = COMMISSION_STATUS_PENDING
        commission.confirmed_at = None
        _append_tx(
            db,
            user_id=commission.referrer_user_id,
            tx_type="commission_revert_premature",
            amount=Decimal("0"),
            wallet=wallet,
            reference_type="commission",
            reference_id=commission.id,
            description=f"Điều chỉnh hoa hồng chờ giao đơn #{order.order_code or order.id}",
        )
        fixed += 1

    if fixed:
        db.commit()
        logger.info("repair_premature_commission_confirmations fixed=%s", fixed)
    return fixed


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
        db.query(func.count(Order.id))
        .filter(Order.referrer_user_id == user_id)
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
