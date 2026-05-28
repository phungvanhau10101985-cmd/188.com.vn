from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.crud import notification as crud_notification
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderStatus
from app.models.promotion import AutoGrantTrigger, GrantStatus, Promotion, PromotionUsage, UserPromotionGrant
from app.models.user import User
from app.schemas.notification import NotificationCreate

logger = logging.getLogger(__name__)

PROMO_WELCOME = "WELCOME188"
PROMO_THANKYOU = "THANKYOU188"
PROMO_COMEBACK = "COMEBACK10"
PROMO_CART_ABANDON = "CARTSAVE188"

LEGACY_WALLET_BDAY_CODE = "BDAY188"

PROMO_TEMPLATES: List[Dict[str, Any]] = [
    {
        "code": PROMO_WELCOME,
        "name": "Quà chào bạn mới",
        "description": "Giảm 10% đơn hàng đầu tiên — quà riêng khi bạn đăng ký.",
        "discount_percent": Decimal("10"),
        "max_discount_amount": Decimal("200000"),
        "first_order_only": True,
        "stack_with_birthday": False,
        "stack_with_loyalty": True,
        "grant_valid_days": 7,
        "auto_grant_trigger": AutoGrantTrigger.SIGNUP,
    },
    {
        "code": PROMO_THANKYOU,
        "name": "Cảm ơn bạn đã mua",
        "description": "Giảm 5% cho đơn tiếp theo — tặng sau khi nhận hàng lần đầu.",
        "discount_percent": Decimal("5"),
        "max_discount_amount": Decimal("100000"),
        "first_order_only": False,
        "stack_with_birthday": False,
        "stack_with_loyalty": True,
        "grant_valid_days": 14,
        "auto_grant_trigger": AutoGrantTrigger.FIRST_DELIVERED,
    },
    {
        "code": PROMO_COMEBACK,
        "name": "Nhớ bạn quay lại",
        "description": "Giảm 10% — quà dành riêng cho khách lâu chưa mua.",
        "discount_percent": Decimal("10"),
        "max_discount_amount": Decimal("100000"),
        "first_order_only": False,
        "stack_with_birthday": False,
        "stack_with_loyalty": True,
        "grant_valid_days": 5,
        "auto_grant_trigger": AutoGrantTrigger.COMEBACK,
    },
    {
        "code": PROMO_CART_ABANDON,
        "name": "Quà nhắc giỏ hàng",
        "description": "Giảm 5% — quà riêng khi bạn để sản phẩm trong giỏ quá lâu chưa đặt.",
        "discount_percent": Decimal("5"),
        "max_discount_amount": Decimal("80000"),
        "first_order_only": False,
        "stack_with_birthday": False,
        "stack_with_loyalty": True,
        "grant_valid_days": 3,
        "auto_grant_trigger": AutoGrantTrigger.CART_ABANDON,
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_promotion_templates(db: Session) -> None:
    from app.crud import promotion as crud_promotion

    for tpl in PROMO_TEMPLATES:
        code = tpl["code"]
        existing = crud_promotion.get_promotion_by_code(db, code)
        if existing:
            existing.name = tpl["name"]
            existing.description = tpl["description"]
            existing.discount_percent = tpl["discount_percent"]
            existing.max_discount_amount = tpl["max_discount_amount"]
            existing.first_order_only = tpl["first_order_only"]
            existing.stack_with_birthday = tpl["stack_with_birthday"]
            existing.stack_with_loyalty = tpl["stack_with_loyalty"]
            existing.requires_wallet_grant = True
            existing.grant_valid_days = tpl["grant_valid_days"]
            existing.auto_grant_trigger = tpl["auto_grant_trigger"].value
            existing.is_active = True
            if code == PROMO_WELCOME:
                existing.eligible_within_days = tpl["grant_valid_days"]
        else:
            db.add(
                Promotion(
                    code=code,
                    name=tpl["name"],
                    description=tpl["description"],
                    discount_percent=tpl["discount_percent"],
                    max_discount_amount=tpl["max_discount_amount"],
                    first_order_only=tpl["first_order_only"],
                    stack_with_birthday=tpl["stack_with_birthday"],
                    stack_with_loyalty=tpl["stack_with_loyalty"],
                    requires_wallet_grant=True,
                    grant_valid_days=tpl["grant_valid_days"],
                    auto_grant_trigger=tpl["auto_grant_trigger"].value,
                    is_active=True,
                    per_user_limit=1,
                    eligible_within_days=tpl["grant_valid_days"] if code == PROMO_WELCOME else None,
                )
            )
    db.commit()
    purge_legacy_bday188_wallet_promo(db)


def purge_legacy_bday188_wallet_promo(db: Session) -> bool:
    """Xóa mã ví BDAY188 — sinh nhật dùng CMSN tự động (birthday_discount), không qua ví."""
    from app.crud import promotion as crud_promotion

    promo = crud_promotion.get_promotion_by_code(db, LEGACY_WALLET_BDAY_CODE)
    if not promo:
        return True
    promo_id = promo.id
    db.query(PromotionUsage).filter(PromotionUsage.promotion_id == promo_id).delete(
        synchronize_session=False
    )
    db.query(UserPromotionGrant).filter(UserPromotionGrant.promotion_id == promo_id).delete(
        synchronize_session=False
    )
    db.delete(promo)
    db.commit()
    logger.info("Removed legacy wallet promo %s", LEGACY_WALLET_BDAY_CODE)
    return True


def expire_stale_grants(db: Session, *, user_id: Optional[int] = None) -> int:
    now = _utc_now()
    q = db.query(UserPromotionGrant).filter(
        UserPromotionGrant.status == GrantStatus.ACTIVE.value,
        UserPromotionGrant.expires_at.isnot(None),
        UserPromotionGrant.expires_at < now,
    )
    if user_id is not None:
        q = q.filter(UserPromotionGrant.user_id == user_id)
    count = 0
    for grant in q.all():
        grant.status = GrantStatus.EXPIRED.value
        count += 1
    if count:
        db.commit()
    return count


def _resolve_grant_expires_at(promotion: Promotion, *, granted_at: datetime) -> Optional[datetime]:
    days = promotion.grant_valid_days or promotion.eligible_within_days
    if days is None or int(days) <= 0:
        return None
    return _as_utc(granted_at) + timedelta(days=int(days))


def _has_active_grant(db: Session, user_id: int, promotion_id: int) -> bool:
    expire_stale_grants(db, user_id=user_id)
    return (
        db.query(UserPromotionGrant.id)
        .filter(
            UserPromotionGrant.user_id == user_id,
            UserPromotionGrant.promotion_id == promotion_id,
            UserPromotionGrant.status == GrantStatus.ACTIVE.value,
        )
        .first()
        is not None
    )


def _notify_grant(db: Session, *, user_id: int, promotion: Promotion, days: int, message: str) -> None:
    try:
        crud_notification.create_notification(
            db,
            NotificationCreate(
                user_id=user_id,
                title=f"Bạn nhận quà: {promotion.name}",
                content=(
                    f"{message} Mã {promotion.code} — giảm {promotion.discount_percent}% "
                    f"(tối đa {int(promotion.max_discount_amount or 0):,}đ). "
                    f"Hết hạn sau {days} ngày. Xem tại mục Khuyến mãi."
                ).replace(",", "."),
                type="promotion",
            ),
        )
    except Exception as exc:
        logger.warning("grant notification failed user=%s: %s", user_id, exc)


def grant_voucher(
    db: Session,
    *,
    user_id: int,
    promo_code: str,
    source: str,
    expires_in_days: Optional[int] = None,
    grant_message: Optional[str] = None,
    notify: bool = True,
    skip_if_active: bool = True,
) -> Optional[UserPromotionGrant]:
    from app.crud import promotion as crud_promotion

    promotion = crud_promotion.get_promotion_by_code(db, promo_code)
    if not promotion or not promotion.is_active:
        return None

    if skip_if_active and _has_active_grant(db, user_id, promotion.id):
        return None

    now = _utc_now()
    days = expires_in_days or promotion.grant_valid_days or promotion.eligible_within_days or 7
    expires_at = _as_utc(now) + timedelta(days=int(days))

    grant = UserPromotionGrant(
        user_id=user_id,
        promotion_id=promotion.id,
        granted_at=now,
        expires_at=expires_at,
        source=source,
        status=GrantStatus.ACTIVE.value,
        grant_message=grant_message,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    if notify:
        msg = grant_message or f"Shop tặng bạn mã {promotion.code}."
        _notify_grant(db, user_id=user_id, promotion=promotion, days=int(days), message=msg)
    return grant


def process_signup_grants(db: Session, user_id: int) -> None:
    ensure_promotion_templates(db)
    grant_voucher(db, user_id=user_id, promo_code=PROMO_WELCOME, source="signup", notify=True)


def _count_delivered_orders(db: Session, user_id: int) -> int:
    return (
        db.query(Order.id)
        .filter(
            Order.user_id == user_id,
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]),
        )
        .count()
    )


def process_first_delivered_grants(db: Session, user_id: int) -> None:
    if _count_delivered_orders(db, user_id) != 1:
        return
    grant_voucher(
        db,
        user_id=user_id,
        promo_code=PROMO_THANKYOU,
        source="first_delivered",
        grant_message="Cảm ơn bạn đã tin tưởng shop — đây là quà cho lần mua tiếp theo.",
    )


def process_comeback_grants_for_all(db: Session, *, inactive_days: int = 30) -> Dict[str, int]:
    """Tặng COMEBACK cho khách có đơn giao thành công nhưng lâu chưa mua lại."""
    ensure_promotion_templates(db)
    cutoff = _utc_now() - timedelta(days=inactive_days)
    promo = db.query(Promotion).filter(Promotion.code == PROMO_COMEBACK).first()
    if not promo:
        return {"granted": 0, "skipped": 0}

    users_with_orders = (
        db.query(Order.user_id)
        .filter(
            Order.user_id.isnot(None),
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]),
        )
        .distinct()
        .all()
    )
    granted = 0
    skipped = 0
    for (user_id,) in users_with_orders:
        if not user_id:
            continue
        last_order = (
            db.query(Order.created_at)
            .filter(
                Order.user_id == user_id,
                Order.status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]),
            )
            .order_by(Order.created_at.desc())
            .first()
        )
        if not last_order or not last_order[0] or _as_utc(last_order[0]) > cutoff:
            skipped += 1
            continue
        if _has_active_grant(db, user_id, promo.id):
            skipped += 1
            continue
        g = grant_voucher(
            db,
            user_id=user_id,
            promo_code=PROMO_COMEBACK,
            source="comeback",
            skip_if_active=False,
            grant_message="Shop nhớ bạn! Quay lại với ưu đãi riêng.",
        )
        if g:
            granted += 1
        else:
            skipped += 1
    return {"granted": granted, "skipped": skipped}


def _user_ever_had_welcome(db: Session, user_id: int, welcome_promo_id: int) -> bool:
    from app.crud import promotion as crud_promotion

    if crud_promotion.user_promo_usage_count(db, user_id=user_id, promotion_id=welcome_promo_id) > 0:
        return True
    return (
        db.query(UserPromotionGrant.id)
        .filter(
            UserPromotionGrant.user_id == user_id,
            UserPromotionGrant.promotion_id == welcome_promo_id,
        )
        .first()
        is not None
    )


def process_welcome_backfill(db: Session) -> Dict[str, int]:
    """Tặng WELCOME188 cho user cũ: chưa có đơn, chưa từng có/grant hoặc dùng WELCOME."""
    from app.crud import promotion as crud_promotion

    ensure_promotion_templates(db)
    welcome = crud_promotion.get_promotion_by_code(db, PROMO_WELCOME)
    if not welcome:
        return {"granted": 0, "skipped": 0}

    user_ids = [row[0] for row in db.query(User.id).all()]
    granted = 0
    skipped = 0
    for user_id in user_ids:
        if crud_promotion.user_has_non_cancelled_order(db, user_id):
            skipped += 1
            continue
        if _user_ever_had_welcome(db, user_id, welcome.id):
            skipped += 1
            continue
        g = grant_voucher(
            db,
            user_id=user_id,
            promo_code=PROMO_WELCOME,
            source="welcome_backfill",
            grant_message="Shop gửi bạn quà chào mừng — dành riêng cho đơn hàng đầu tiên.",
            skip_if_active=False,
        )
        if g:
            granted += 1
        else:
            skipped += 1
    return {"granted": granted, "skipped": skipped}


def _cart_last_touch(cart: Cart) -> datetime:
    touches: List[datetime] = []
    if cart.updated_at:
        touches.append(_as_utc(cart.updated_at))
    if cart.created_at:
        touches.append(_as_utc(cart.created_at))
    for item in cart.items or []:
        if item.updated_at:
            touches.append(_as_utc(item.updated_at))
        if item.added_at:
            touches.append(_as_utc(item.added_at))
        if item.created_at:
            touches.append(_as_utc(item.created_at))
    return max(touches) if touches else _utc_now()


def process_cart_abandon_grants_for_all(
    db: Session,
    *,
    abandon_hours: int = 24,
    cooldown_days: int = 7,
) -> Dict[str, int]:
    """Tặng CARTSAVE188 cho khách có giỏ treo lâu chưa đặt hàng."""
    ensure_promotion_templates(db)
    promo = db.query(Promotion).filter(Promotion.code == PROMO_CART_ABANDON).first()
    if not promo:
        return {"granted": 0, "skipped": 0}

    now = _utc_now()
    cutoff = now - timedelta(hours=abandon_hours)
    cooldown_cutoff = now - timedelta(days=cooldown_days)

    carts = (
        db.query(Cart)
        .options(joinedload(Cart.items))
        .join(CartItem)
        .distinct()
        .all()
    )
    granted = 0
    skipped = 0
    for cart in carts:
        user_id = cart.user_id
        if not cart.items:
            skipped += 1
            continue

        last_touch = _cart_last_touch(cart)
        if last_touch > cutoff:
            skipped += 1
            continue

        ordered_after_cart = (
            db.query(Order.id)
            .filter(
                Order.user_id == user_id,
                Order.status != OrderStatus.CANCELLED,
                Order.created_at >= last_touch,
            )
            .first()
        )
        if ordered_after_cart:
            skipped += 1
            continue

        recent_abandon_grant = (
            db.query(UserPromotionGrant.id)
            .filter(
                UserPromotionGrant.user_id == user_id,
                UserPromotionGrant.promotion_id == promo.id,
                UserPromotionGrant.source == "cart_abandon",
                UserPromotionGrant.granted_at >= cooldown_cutoff,
            )
            .first()
        )
        if recent_abandon_grant:
            skipped += 1
            continue

        if _has_active_grant(db, user_id, promo.id):
            skipped += 1
            continue

        g = grant_voucher(
            db,
            user_id=user_id,
            promo_code=PROMO_CART_ABANDON,
            source="cart_abandon",
            skip_if_active=False,
            grant_message="Bạn còn sản phẩm trong giỏ — shop gửi thêm ưu đãi để bạn hoàn tất đơn nhé.",
        )
        if g:
            granted += 1
        else:
            skipped += 1
    return {"granted": granted, "skipped": skipped}


def get_active_grant(
    db: Session,
    *,
    user_id: int,
    promotion_id: int,
) -> Optional[UserPromotionGrant]:
    expire_stale_grants(db, user_id=user_id)
    return (
        db.query(UserPromotionGrant)
        .filter(
            UserPromotionGrant.user_id == user_id,
            UserPromotionGrant.promotion_id == promotion_id,
            UserPromotionGrant.status == GrantStatus.ACTIVE.value,
        )
        .order_by(UserPromotionGrant.granted_at.desc())
        .first()
    )


def mark_grant_used(
    db: Session,
    *,
    user_id: int,
    promotion_id: int,
    order_id: int,
) -> Optional[UserPromotionGrant]:
    grant = get_active_grant(db, user_id=user_id, promotion_id=promotion_id)
    if not grant:
        return None
    grant.status = GrantStatus.USED.value
    grant.used_order_id = order_id
    grant.used_at = _utc_now()
    db.flush()
    return grant


def build_wallet_voucher_item(
    db: Session,
    user: User,
    grant: UserPromotionGrant,
    *,
    subtotal: Optional[Decimal] = None,
) -> Dict[str, Any]:
    from app.crud import promotion as crud_promotion

    promotion = grant.promotion or db.query(Promotion).filter(Promotion.id == grant.promotion_id).first()
    if not promotion:
        return {}

    eligible, reason = crud_promotion.is_promotion_eligible(
        db,
        user.id,
        promotion,
        user=user,
        grant=grant,
    )
    expires_at = grant.expires_at
    days_remaining = crud_promotion.get_days_remaining(expires_at)

    estimated_discount: Optional[float] = None
    if eligible and subtotal is not None and subtotal > 0:
        amount = crud_promotion.calculate_percent_discount(
            subtotal,
            percent=Decimal(str(promotion.discount_percent)),
            max_discount=(
                Decimal(str(promotion.max_discount_amount))
                if promotion.max_discount_amount is not None
                else None
            ),
        )
        if amount > 0:
            estimated_discount = float(amount)

    return {
        "grant_id": grant.id,
        "code": promotion.code,
        "name": promotion.name,
        "description": grant.grant_message or promotion.description,
        "discount_percent": float(promotion.discount_percent),
        "max_discount_amount": float(promotion.max_discount_amount or 0),
        "eligible": eligible,
        "reason": reason,
        "show_days_remaining": expires_at is not None,
        "days_remaining": days_remaining,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "granted_at": grant.granted_at.isoformat() if grant.granted_at else None,
        "source": grant.source,
        "is_new": (_utc_now() - _as_utc(grant.granted_at)).total_seconds() < 86400 if grant.granted_at else False,
        "estimated_discount": estimated_discount,
    }


def list_wallet_vouchers(
    db: Session,
    user: User,
    *,
    subtotal: Optional[Decimal] = None,
) -> List[Dict[str, Any]]:
    expire_stale_grants(db, user_id=user.id)
    grants = (
        db.query(UserPromotionGrant)
        .filter(
            UserPromotionGrant.user_id == user.id,
            UserPromotionGrant.status == GrantStatus.ACTIVE.value,
        )
        .order_by(UserPromotionGrant.granted_at.desc())
        .all()
    )
    items = [build_wallet_voucher_item(db, user, g, subtotal=subtotal) for g in grants]
    items = [i for i in items if i]
    items.sort(key=lambda row: (not row["eligible"], not row.get("is_new"), row["code"]))
    return items
