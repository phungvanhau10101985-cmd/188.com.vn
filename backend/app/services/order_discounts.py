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


def apply_promo_discount_cap(
    *,
    max_promo_amount: Decimal,
    welcome: Decimal,
    birthday: Decimal,
    loyalty: Decimal,
) -> tuple[Decimal, Decimal, Decimal, bool]:
    """Cắt tổng voucher/sinh nhật/hạng về tối đa max_promo_amount (ưu tiên cắt loyalty trước)."""
    welcome = max(Decimal("0"), welcome)
    birthday = max(Decimal("0"), birthday)
    loyalty = max(Decimal("0"), loyalty)
    max_total = max(Decimal("0"), max_promo_amount)
    total = welcome + birthday + loyalty
    if total <= max_total:
        return welcome, birthday, loyalty, False

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

    return welcome, birthday, loyalty, True


def apply_total_discount_cap(
    *,
    subtotal: Decimal,
    welcome: Decimal,
    birthday: Decimal,
    loyalty: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Nếu tổng giảm promo > 15% subtotal thì cắt về 15% (ưu tiên giảm loyalty trước)."""
    welcome, birthday, loyalty, _ = apply_promo_discount_cap(
        max_promo_amount=max_order_discount_amount(subtotal),
        welcome=welcome,
        birthday=birthday,
        loyalty=loyalty,
    )
    return welcome, birthday, loyalty


def apply_grand_discount_cap(
    *,
    list_subtotal: Decimal,
    site_sale_savings: Decimal,
    welcome: Decimal,
    birthday: Decimal,
    loyalty: Decimal,
) -> tuple[Decimal, Decimal, Decimal, bool]:
    """
    Trần 15% trên giá gốc (list): site sale + voucher/sinh nhật/hạng không vượt 15%.
    Ví dụ sale 6% + sinh nhật 10% = 16% → chỉ còn 15% (cắt phần promo dư).
    """
    list_base = max(Decimal("0"), list_subtotal)
    site_savings = max(Decimal("0"), site_sale_savings)
    max_total = max_order_discount_amount(list_base)
    promo_budget = max(Decimal("0"), max_total - site_savings)
    raw_promo = max(Decimal("0"), welcome) + max(Decimal("0"), birthday) + max(Decimal("0"), loyalty)
    welcome, birthday, loyalty, promo_capped = apply_promo_discount_cap(
        max_promo_amount=promo_budget,
        welcome=welcome,
        birthday=birthday,
        loyalty=loyalty,
    )
    capped = promo_capped or (site_savings + raw_promo) > max_total
    return welcome, birthday, loyalty, capped


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
    list_subtotal: Optional[Decimal] = None,
) -> OrderDiscountBreakdown:
    """
    Mã ví HOẶC sinh nhật, sau đó có thể cộng hạng thành viên trên phần còn lại.
    Tổng giảm (site sale + promo) tối đa 15% giá gốc list_subtotal.
    """
    breakdown = OrderDiscountBreakdown(subtotal=subtotal)
    if user is None or subtotal <= 0:
        return breakdown

    list_base = list_subtotal if list_subtotal is not None else subtotal
    site_sale_savings = max(Decimal("0"), list_base - subtotal)

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

    welcome_amount, birthday_amount, loyalty_amount, breakdown.discount_capped = apply_grand_discount_cap(
        list_subtotal=list_base,
        site_sale_savings=site_sale_savings,
        welcome=welcome_amount,
        birthday=birthday_amount,
        loyalty=loyalty_amount,
    )

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
            f"Tổng ưu đãi (sale + mã/sinh nhật/hạng) được giới hạn tối đa {MAX_ORDER_DISCOUNT_PERCENT}% giá gốc đơn hàng."
        )

    return breakdown
