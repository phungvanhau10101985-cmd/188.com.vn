from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus
from app.models.promotion import AutoGrantTrigger, GrantStatus, Promotion, PromotionUsage, UserPromotionGrant
from app.models.user import User
from app.services import promotion_grants as grant_svc

PROMO_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,50}$")
VALID_AUTO_GRANT_TRIGGERS = {t.value for t in AutoGrantTrigger}

WELCOME_PROMO_CODE = "WELCOME188"
WELCOME_DISCOUNT_PERCENT = Decimal("10")
WELCOME_MAX_DISCOUNT = Decimal("200000")
WELCOME_DEFAULT_ELIGIBLE_DAYS = 7


class PromoValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_promo_code(code: str) -> str:
    return (code or "").strip().upper()


def get_promotion_by_code(db: Session, code: str) -> Optional[Promotion]:
    normalized = normalize_promo_code(code)
    if not normalized:
        return None
    return db.query(Promotion).filter(Promotion.code == normalized).first()


def get_promotion_by_id(db: Session, promotion_id: int) -> Optional[Promotion]:
    return db.query(Promotion).filter(Promotion.id == promotion_id).first()


def _validate_promo_code(code: str) -> str:
    normalized = normalize_promo_code(code)
    if not normalized or not PROMO_CODE_PATTERN.match(normalized):
        raise PromoValidationError("Mã chỉ gồm chữ in hoa, số và dấu gạch dưới (2–50 ký tự).")
    return normalized


def _parse_optional_datetime(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PromoValidationError("Ngày giờ không hợp lệ.") from exc
    return _as_utc(parsed)


def _validate_auto_grant_trigger(value: str) -> str:
    trigger = (value or AutoGrantTrigger.NONE.value).strip().lower()
    if trigger not in VALID_AUTO_GRANT_TRIGGERS:
        raise PromoValidationError("Trigger tự động tặng mã không hợp lệ.")
    return trigger


def list_all_promotions(db: Session) -> List[Promotion]:
    grant_svc.ensure_promotion_templates(db)
    return db.query(Promotion).order_by(Promotion.is_active.desc(), Promotion.code.asc()).all()


def get_promotion_stats(db: Session, promotion_id: int) -> Tuple[int, int]:
    grants_count = (
        db.query(UserPromotionGrant)
        .filter(UserPromotionGrant.promotion_id == promotion_id)
        .count()
    )
    usages_count = (
        db.query(PromotionUsage)
        .filter(PromotionUsage.promotion_id == promotion_id)
        .count()
    )
    return grants_count, usages_count


def create_promotion(db: Session, data: Dict[str, Any]) -> Promotion:
    code = _validate_promo_code(data["code"])
    if get_promotion_by_code(db, code):
        raise PromoValidationError(f"Mã {code} đã tồn tại.")

    trigger = _validate_auto_grant_trigger(data.get("auto_grant_trigger", AutoGrantTrigger.NONE.value))
    promo = Promotion(
        code=code,
        name=(data.get("name") or "").strip(),
        description=data.get("description"),
        discount_percent=Decimal(str(data["discount_percent"])),
        max_discount_amount=(
            Decimal(str(data["max_discount_amount"]))
            if data.get("max_discount_amount") is not None
            else None
        ),
        first_order_only=bool(data.get("first_order_only", True)),
        stack_with_birthday=bool(data.get("stack_with_birthday", False)),
        stack_with_loyalty=bool(data.get("stack_with_loyalty", True)),
        is_active=bool(data.get("is_active", True)),
        valid_from=_parse_optional_datetime(data.get("valid_from")),
        valid_to=_parse_optional_datetime(data.get("valid_to")),
        usage_limit=data.get("usage_limit"),
        per_user_limit=int(data.get("per_user_limit") or 1),
        eligible_within_days=data.get("eligible_within_days"),
        grant_valid_days=data.get("grant_valid_days"),
        requires_wallet_grant=bool(data.get("requires_wallet_grant", True)),
        auto_grant_trigger=trigger,
    )
    if not promo.name:
        raise PromoValidationError("Tên chương trình không được để trống.")
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


def update_promotion(db: Session, promotion_id: int, data: Dict[str, Any]) -> Promotion:
    promo = get_promotion_by_id(db, promotion_id)
    if not promo:
        raise PromoValidationError("Không tìm thấy mã khuyến mãi.")

    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise PromoValidationError("Tên chương trình không được để trống.")
        promo.name = name
    if "description" in data:
        promo.description = data["description"]
    if "discount_percent" in data and data["discount_percent"] is not None:
        promo.discount_percent = Decimal(str(data["discount_percent"]))
    if "max_discount_amount" in data:
        promo.max_discount_amount = (
            Decimal(str(data["max_discount_amount"]))
            if data["max_discount_amount"] is not None
            else None
        )
    if "first_order_only" in data and data["first_order_only"] is not None:
        promo.first_order_only = bool(data["first_order_only"])
    if "stack_with_birthday" in data and data["stack_with_birthday"] is not None:
        promo.stack_with_birthday = bool(data["stack_with_birthday"])
    if "stack_with_loyalty" in data and data["stack_with_loyalty"] is not None:
        promo.stack_with_loyalty = bool(data["stack_with_loyalty"])
    if "is_active" in data and data["is_active"] is not None:
        promo.is_active = bool(data["is_active"])
    if "valid_from" in data:
        promo.valid_from = _parse_optional_datetime(data["valid_from"])
    if "valid_to" in data:
        promo.valid_to = _parse_optional_datetime(data["valid_to"])
    if "usage_limit" in data:
        promo.usage_limit = data["usage_limit"]
    if "per_user_limit" in data and data["per_user_limit"] is not None:
        promo.per_user_limit = int(data["per_user_limit"])
    if "eligible_within_days" in data:
        raw_days = data["eligible_within_days"]
        promo.eligible_within_days = None if raw_days in (None, 0) else int(raw_days)
    if "grant_valid_days" in data:
        promo.grant_valid_days = data["grant_valid_days"]
    if "requires_wallet_grant" in data and data["requires_wallet_grant"] is not None:
        promo.requires_wallet_grant = bool(data["requires_wallet_grant"])
    if "auto_grant_trigger" in data and data["auto_grant_trigger"] is not None:
        promo.auto_grant_trigger = _validate_auto_grant_trigger(data["auto_grant_trigger"])

    db.commit()
    db.refresh(promo)
    return promo


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_days_remaining(expires_at: Optional[datetime]) -> Optional[int]:
    if expires_at is None:
        return None
    diff_seconds = (_as_utc(expires_at) - datetime.now(timezone.utc)).total_seconds()
    if diff_seconds <= 0:
        return 0
    return int((diff_seconds + 86399) // 86400)


def user_has_non_cancelled_order(db: Session, user_id: int) -> bool:
    return (
        db.query(Order.id)
        .filter(
            Order.user_id == user_id,
            Order.status != OrderStatus.CANCELLED,
        )
        .first()
        is not None
    )


def user_promo_usage_count(db: Session, *, user_id: int, promotion_id: int) -> int:
    return (
        db.query(PromotionUsage)
        .filter(
            PromotionUsage.user_id == user_id,
            PromotionUsage.promotion_id == promotion_id,
        )
        .count()
    )


def is_promotion_eligible(
    db: Session,
    user_id: int,
    promotion: Promotion,
    *,
    user: Optional[User] = None,
    grant: Optional[UserPromotionGrant] = None,
) -> Tuple[bool, str]:
    if not promotion.is_active:
        return False, "Mã khuyến mãi không còn hiệu lực."

    now = datetime.now(timezone.utc)
    if promotion.valid_from and now < _as_utc(promotion.valid_from):
        return False, "Mã khuyến mãi chưa đến thời gian áp dụng."
    if promotion.valid_to and now > _as_utc(promotion.valid_to):
        return False, "Mã khuyến mãi đã hết hạn."

    if getattr(promotion, "requires_wallet_grant", True):
        if grant is None:
            grant = grant_svc.get_active_grant(db, user_id=user_id, promotion_id=promotion.id)
        if not grant:
            return False, "Mã chưa có trong ví khuyến mãi của bạn."
        if grant.status != GrantStatus.ACTIVE.value:
            return False, "Mã đã được dùng hoặc đã hết hạn."
        if grant.expires_at and now > _as_utc(grant.expires_at):
            return False, "Mã khuyến mãi đã hết hạn."

    if promotion.first_order_only and user_has_non_cancelled_order(db, user_id):
        return False, "Ưu đãi chỉ áp dụng cho đơn hàng đầu tiên."

    per_user_limit = promotion.per_user_limit or 1
    used_count = user_promo_usage_count(db, user_id=user_id, promotion_id=promotion.id)
    if used_count >= per_user_limit:
        return False, "Bạn đã sử dụng mã khuyến mãi này."

    if promotion.usage_limit is not None:
        total_used = db.query(PromotionUsage).filter(PromotionUsage.promotion_id == promotion.id).count()
        if total_used >= promotion.usage_limit:
            return False, "Mã khuyến mãi đã hết lượt sử dụng."

    return True, ""


def is_welcome_eligible(
    db: Session,
    user_id: int,
    promotion: Promotion,
    *,
    user: Optional[User] = None,
) -> Tuple[bool, str]:
    return is_promotion_eligible(db, user_id, promotion, user=user)


def build_welcome_status(db: Session, user: User) -> Dict[str, Any]:
    grant_svc.ensure_promotion_templates(db)
    items = grant_svc.list_wallet_vouchers(db, user)
    welcome = next((i for i in items if i.get("code") == WELCOME_PROMO_CODE), None)
    if welcome:
        return {
            "eligible": welcome["eligible"],
            "code": welcome["code"],
            "name": welcome["name"],
            "description": welcome.get("description"),
            "discount_percent": welcome["discount_percent"],
            "max_discount_amount": welcome["max_discount_amount"],
            "eligible_within_days": None,
            "show_days_remaining": welcome.get("show_days_remaining", False),
            "days_remaining": welcome.get("days_remaining"),
            "expires_at": welcome.get("expires_at"),
            "reason": welcome.get("reason"),
            "is_active": True,
        }
    return {
        "eligible": False,
        "code": WELCOME_PROMO_CODE,
        "name": "Quà chào bạn mới",
        "discount_percent": float(WELCOME_DISCOUNT_PERCENT),
        "max_discount_amount": float(WELCOME_MAX_DISCOUNT),
        "show_days_remaining": False,
        "days_remaining": None,
        "expires_at": None,
        "reason": "Bạn chưa có mã quà chào mừng trong ví.",
        "is_active": True,
    }


def list_user_vouchers(
    db: Session,
    user: User,
    *,
    subtotal: Optional[Decimal] = None,
) -> list[Dict[str, Any]]:
    grant_svc.ensure_promotion_templates(db)
    return grant_svc.list_wallet_vouchers(db, user, subtotal=subtotal)


def calculate_percent_discount(
    subtotal: Decimal,
    *,
    percent: Decimal,
    max_discount: Optional[Decimal],
) -> Decimal:
    if subtotal <= 0 or percent <= 0:
        return Decimal("0")
    raw = (subtotal * percent) / 100
    if max_discount is not None:
        raw = min(raw, max_discount)
    return raw.quantize(Decimal("1"))


def validate_welcome_promo(
    db: Session,
    *,
    user_id: int,
    code: str,
    subtotal: Decimal,
) -> Tuple[Optional[Promotion], Decimal, str, Optional[UserPromotionGrant]]:
    normalized = normalize_promo_code(code)
    if not normalized:
        raise PromoValidationError("Vui lòng chọn mã khuyến mãi.")

    promotion = get_promotion_by_code(db, normalized)
    if not promotion:
        raise PromoValidationError("Mã khuyến mãi không hợp lệ.")

    grant = grant_svc.get_active_grant(db, user_id=user_id, promotion_id=promotion.id)
    eligible, reason = is_promotion_eligible(db, user_id, promotion, grant=grant)
    if not eligible:
        raise PromoValidationError(reason)

    amount = calculate_percent_discount(
        subtotal,
        percent=Decimal(str(promotion.discount_percent)),
        max_discount=(
            Decimal(str(promotion.max_discount_amount))
            if promotion.max_discount_amount is not None
            else None
        ),
    )
    if amount <= 0:
        raise PromoValidationError("Giá trị đơn hàng chưa đủ điều kiện áp dụng mã.")

    note = f"Ưu đãi {promotion.code} ({promotion.discount_percent}%): -{amount:,.0f} đ"
    return promotion, amount, note, grant


def get_welcome_promotion(db: Session) -> Optional[Promotion]:
    return get_promotion_by_code(db, WELCOME_PROMO_CODE)


def update_welcome_promotion(db: Session, data: Dict[str, Any]) -> Promotion:
    grant_svc.ensure_promotion_templates(db)
    promo = get_welcome_promotion(db)
    if not promo:
        grant_svc.ensure_promotion_templates(db)
        promo = get_welcome_promotion(db)
    if not promo:
        raise PromoValidationError("Không tìm thấy chương trình WELCOME188.")

    if "eligible_within_days" in data:
        raw_days = data["eligible_within_days"]
        days = None if raw_days in (None, 0) else int(raw_days)
        promo.eligible_within_days = days
        promo.grant_valid_days = days
    if "discount_percent" in data and data["discount_percent"] is not None:
        promo.discount_percent = Decimal(str(data["discount_percent"]))
    if "max_discount_amount" in data and data["max_discount_amount"] is not None:
        promo.max_discount_amount = Decimal(str(data["max_discount_amount"]))
    if "is_active" in data and data["is_active"] is not None:
        promo.is_active = bool(data["is_active"])
    if "description" in data:
        promo.description = data["description"]
    if "name" in data and data["name"]:
        promo.name = data["name"]
    db.commit()
    db.refresh(promo)
    return promo


def record_promotion_usage(
    db: Session,
    *,
    promotion: Promotion,
    user_id: int,
    order_id: int,
    discount_amount: Decimal,
    grant_id: Optional[int] = None,
) -> PromotionUsage:
    usage = PromotionUsage(
        promotion_id=promotion.id,
        user_id=user_id,
        order_id=order_id,
        discount_amount=discount_amount,
        grant_id=grant_id,
    )
    db.add(usage)
    db.flush()
    return usage


def ensure_welcome_promotion(db: Session) -> Promotion:
    grant_svc.ensure_promotion_templates(db)
    promo = get_welcome_promotion(db)
    if not promo:
        raise PromoValidationError("WELCOME188 chưa được cấu hình.")
    return promo
