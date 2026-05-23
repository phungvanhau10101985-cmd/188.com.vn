"""Build cart discount fields from order discount breakdown."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.order_discounts import calculate_order_discounts


def build_cart_discount_fields(
    db: Session,
    *,
    user: User,
    total_price: float,
    promo_code: Optional[str] = None,
) -> dict:
    subtotal = Decimal(str(total_price))
    breakdown = calculate_order_discounts(
        db,
        user=user,
        subtotal=subtotal,
        promo_code=promo_code,
    )
    from app.crud import promotion as crud_promotion

    wallet_items = crud_promotion.list_user_vouchers(db, user, subtotal=subtotal)
    welcome_eligible = any(i.get("code") == "WELCOME188" and i.get("eligible") for i in wallet_items)

    return {
        "loyalty_discount_percent": breakdown.loyalty_discount_percent,
        "loyalty_discount_amount": float(breakdown.loyalty_discount_amount),
        "loyalty_tier_name": breakdown.loyalty_tier_name,
        "birthday_discount_active": breakdown.birthday_active,
        "birthday_discount_percent": breakdown.birthday_discount_percent,
        "birthday_discount_amount": float(breakdown.birthday_discount_amount),
        "welcome_promo_eligible": welcome_eligible,
        "welcome_promo_applied": breakdown.welcome_applied,
        "welcome_discount_percent": breakdown.welcome_discount_percent,
        "welcome_discount_amount": float(breakdown.welcome_discount_amount),
        "welcome_promo_code": breakdown.welcome_code,
        "final_price": float(breakdown.final_subtotal),
    }
