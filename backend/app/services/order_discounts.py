from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.crud import loyalty as crud_loyalty
from app.crud import promotion as crud_promotion
from app.crud.promotion import PromoValidationError
from app.models.promotion import Promotion
from app.models.user import User
from app.services.birthday_discount import get_birthday_discount_for_user

MAX_ORDER_DISCOUNT_PERCENT = Decimal("15")


def max_order_discount_amount(subtotal: Decimal) -> Decimal:
    if subtotal <= 0:
        return Decimal("0")
    return ((subtotal * MAX_ORDER_DISCOUNT_PERCENT) / Decimal("100")).quantize(Decimal("1"))


def apply_total_discount_cap(
    *,
    subtotal: Decimal,
    welcome: Decimal,
    birthday: Decimal,
    loyalty: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Nếu tổng giảm > 15% subtotal thì cắt về 15% (ưu tiên giảm loyalty trước)."""
    welcome = max(Decimal("0"), welcome)
    birthday = max(Decimal("0"), birthday)
    loyalty = max(Decimal("0"), loyalty)
    max_total = max_order_discount_amount(subtotal)
    total = welcome + birthday + loyalty
    if total <= max_total:
        return welcome, birthday, loyalty

    overflow = total - max_total

    cut = min(loyalty, overflow)
    loyalty -= cut
    overflow -= cut

    if overflow > 0:
        cut = min(birthday, overflow)
        birthday -= cut
        overflow -= cut

    if overflow > 0:
        cut = min(welcome, overflow)
        welcome -= cut

    return welcome, birthday, loyalty


@dataclass
class OrderDiscountBreakdown:
    subtotal: Decimal
    welcome_discount_amount: Decimal = Decimal("0")
    welcome_discount_percent: float = 0.0
    welcome_applied: bool = False
    welcome_code: Optional[str] = None
    birthday_discount_amount: Decimal = Decimal("0")
    birthday_discount_percent: float = 0.0
    birthday_active: bool = False
    loyalty_discount_amount: Decimal = Decimal("0")
    loyalty_discount_percent: float = 0.0
    loyalty_tier_name: Optional[str] = None
    discount_notes: List[str] = field(default_factory=list)
    applied_promotion: Optional[Promotion] = None
    applied_grant_id: Optional[int] = None
    discount_capped: bool = False

    @property
    def total_discount(self) -> Decimal:
        return (
            self.welcome_discount_amount
            + self.birthday_discount_amount
            + self.loyalty_discount_amount
        )

    @property
    def final_subtotal(self) -> Decimal:
        return max(Decimal("0"), self.subtotal - self.total_discount)


def calculate_order_discounts(
    db: Session,
    *,
    user: Optional[User],
    subtotal: Decimal,
    promo_code: Optional[str] = None,
) -> OrderDiscountBreakdown:
    """
    Mã ví HOẶC sinh nhật, sau đó có thể cộng hạng thành viên trên phần còn lại.
    Tổng giảm tối đa 15% subtotal (vd. 19% → còn 15%).
    """
    breakdown = OrderDiscountBreakdown(subtotal=subtotal)
    if user is None or subtotal <= 0:
        return breakdown

    welcome_amount = Decimal("0")
    birthday_amount = Decimal("0")
    loyalty_amount = Decimal("0")
    remaining = subtotal
    promo_applied = False
    promo_note: Optional[str] = None

    normalized_code = (promo_code or "").strip().upper()
    if normalized_code:
        try:
            promo, amount, note, grant = crud_promotion.validate_welcome_promo(
                db,
                user_id=user.id,
                code=normalized_code,
                subtotal=subtotal,
            )
        except PromoValidationError:
            raise
        if promo and amount > 0:
            welcome_amount = amount
            breakdown.welcome_applied = True
            breakdown.welcome_code = promo.code
            breakdown.welcome_discount_percent = float(promo.discount_percent)
            breakdown.applied_promotion = promo
            breakdown.applied_grant_id = grant.id if grant else None
            promo_note = note
            remaining = max(Decimal("0"), subtotal - welcome_amount)
            promo_applied = True

    if not promo_applied:
        birthday_discount = get_birthday_discount_for_user(db, user)
        breakdown.birthday_active = birthday_discount.active
        if birthday_discount.active and birthday_discount.percent > 0:
            birthday_percent = Decimal(str(birthday_discount.percent))
            birthday_amount = (subtotal * birthday_percent) / 100
            breakdown.birthday_discount_percent = float(birthday_discount.percent)
            remaining = max(Decimal("0"), subtotal - birthday_amount)

    total_spent_6_months = crud_loyalty.calculate_user_spend_6_months(db, user.id)
    current_tier = crud_loyalty.get_tier_by_spend(db, total_spent_6_months)
    if current_tier and current_tier.discount_percent > 0 and remaining > 0:
        discount_percent = Decimal(str(current_tier.discount_percent))
        loyalty_amount = (remaining * discount_percent) / 100
        breakdown.loyalty_discount_percent = float(current_tier.discount_percent)
        breakdown.loyalty_tier_name = current_tier.name

    raw_total = welcome_amount + birthday_amount + loyalty_amount
    welcome_amount, birthday_amount, loyalty_amount = apply_total_discount_cap(
        subtotal=subtotal,
        welcome=welcome_amount,
        birthday=birthday_amount,
        loyalty=loyalty_amount,
    )
    capped_total = welcome_amount + birthday_amount + loyalty_amount
    breakdown.discount_capped = capped_total < raw_total

    breakdown.welcome_discount_amount = welcome_amount
    breakdown.birthday_discount_amount = birthday_amount
    breakdown.loyalty_discount_amount = loyalty_amount

    if welcome_amount > 0 and promo_note:
        breakdown.discount_notes.append(promo_note)
    if birthday_amount > 0:
        breakdown.discount_notes.append(
            f"Ưu đãi sinh nhật ({breakdown.birthday_discount_percent}%): -{birthday_amount:,.0f} đ"
        )
    if loyalty_amount > 0 and breakdown.loyalty_tier_name:
        breakdown.discount_notes.append(
            f"Giảm giá thành viên {breakdown.loyalty_tier_name} ({breakdown.loyalty_discount_percent}%): -{loyalty_amount:,.0f} đ"
        )
    if breakdown.discount_capped:
        breakdown.discount_notes.append(
            f"Tổng ưu đãi được giới hạn tối đa {MAX_ORDER_DISCOUNT_PERCENT}% đơn hàng."
        )

    return breakdown
