#!/usr/bin/env python3
"""E2E smoke test: ví mã khuyến mãi + giảm giá + cron."""
from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from app.crud import promotion as crud_promotion
from app.crud.user import create_user
from app.db.session import SessionLocal
from app.models.order import Order
from app.models.product import Product
from app.models.promotion import GrantStatus, UserPromotionGrant
from app.schemas.user import UserCreate
from app.services import promotion_grants as grant_svc
from app.services.order_discounts import apply_total_discount_cap, calculate_order_discounts
from app.services.promotion_cron import run_daily_promotion_cron


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    raise AssertionError(msg)


def main() -> None:
    db = SessionLocal()
    errors: list[str] = []
    uid = uuid.uuid4().hex[:8]
    phone = f"09{int(uuid.uuid4().int % 10**8):08d}"[:10]
    email = f"promo_e2e_{uid}@example.com"

    print("=== E2E Promotion / Wallet ===")

    try:
        # 1. Signup → WELCOME grant
        user = create_user(
            db,
            UserCreate(
                phone=phone,
                email=email,
                full_name=f"E2E Promo {uid}",
            ),
        )
        if not user:
            fail("create_user returned None")
        ok(f"User #{user.id} created ({phone})")

        grants = (
            db.query(UserPromotionGrant)
            .filter(UserPromotionGrant.user_id == user.id)
            .all()
        )
        welcome = [g for g in grants if g.promotion and g.promotion.code == "WELCOME188"]
        if not welcome or welcome[0].status != GrantStatus.ACTIVE.value:
            fail("WELCOME188 grant missing after signup")
        ok(f"WELCOME188 grant id={welcome[0].id}, expires={welcome[0].expires_at}")

        # 2. Wallet list API logic
        items = crud_promotion.list_user_vouchers(db, user, subtotal=Decimal("500000"))
        codes = [i["code"] for i in items if i.get("eligible")]
        if "WELCOME188" not in codes:
            fail(f"WELCOME188 not eligible in wallet: {items}")
        ok(f"Wallet eligible codes: {codes}")

        # 3. Discount cap 15% (10% + 10% on remainder = 19% → 15%)
        w, b, l = apply_total_discount_cap(
            subtotal=Decimal("1000000"),
            welcome=Decimal("100000"),
            birthday=Decimal("0"),
            loyalty=Decimal("90000"),
        )
        total = w + b + l
        if total != Decimal("150000"):
            fail(f"Cap expected 150k, got {total}")
        ok(f"Discount cap math: 19% → 15% = {total:,.0f}đ")

        breakdown = calculate_order_discounts(
            db,
            user=user,
            subtotal=Decimal("1000000"),
            promo_code="WELCOME188",
        )
        if breakdown.total_discount > Decimal("1000000") * Decimal("0.15") + Decimal("1"):
            fail(f"Live discount exceeds 15%: {breakdown.total_discount}")
        ok(
            f"Live discount on 1M: {breakdown.total_discount:,.0f}đ "
            f"(promo={breakdown.welcome_discount_amount}, loyalty={breakdown.loyalty_discount_amount})"
        )

        # 4. Validate promo amount on 500k first order
        b2 = calculate_order_discounts(
            db, user=user, subtotal=Decimal("500000"), promo_code="WELCOME188"
        )
        expected_welcome = Decimal("50000")
        if b2.welcome_discount_amount != expected_welcome:
            fail(f"Expected welcome 50k on 500k, got {b2.welcome_discount_amount}")
        ok(f"WELCOME 10% on 500k = {b2.welcome_discount_amount:,.0f}đ")

        # 5. Mark grant used (simulate checkout)
        promo = crud_promotion.get_promotion_by_code(db, "WELCOME188")
        assert promo
        product = db.query(Product).filter(Product.is_active == True).first()  # noqa: E712
        if not product:
            print("  SKIP  order create — no active product in DB")
        else:
            from app.crud import order as crud_order
            from app.models.order import OrderStatus

            order = crud_order.create_order_with_deposit(
                db=db,
                user_id=user.id,
                customer_name=user.full_name or "Test",
                customer_phone=phone,
                customer_email=email,
                customer_address="123 Test St, Q1, HCM",
                customer_note="E2E promo test",
                payment_method="cod",
                shipping_method=None,
                subtotal=Decimal("500000"),
                shipping_fee=Decimal("0"),
                discount_amount=b2.total_discount,
                total_amount=Decimal("500000") - b2.total_discount,
                admin_notes="; ".join(b2.discount_notes),
                requires_deposit=False,
                deposit_type=None,
                deposit_percentage=0,
                deposit_amount=Decimal("0"),
                remaining_amount=Decimal("500000") - b2.total_discount,
                items=[
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "product_image": product.main_image,
                        "unit_price": float(product.price or 500000),
                        "quantity": 1,
                        "total_price": 500000.0,
                        "selected_size": None,
                        "selected_color": None,
                        "selected_color_name": None,
                        "requires_deposit": False,
                        "deposit_amount": 0,
                    }
                ],
                referrer_user_id=None,
            )
            grant_svc.mark_grant_used(
                db,
                user_id=user.id,
                promotion_id=promo.id,
                order_id=order.id,
            )
            crud_promotion.record_promotion_usage(
                db,
                promotion=promo,
                user_id=user.id,
                order_id=order.id,
                discount_amount=b2.welcome_discount_amount,
                grant_id=welcome[0].id,
            )
            db.commit()
            db.refresh(welcome[0])
            if welcome[0].status != GrantStatus.USED.value:
                fail(f"Grant not marked used: {welcome[0].status}")
            ok(f"Order #{order.id} created, grant marked used")

            # 6. WELCOME no longer eligible (grant used)
            try:
                calculate_order_discounts(
                    db, user=user, subtotal=Decimal("500000"), promo_code="WELCOME188"
                )
                fail("WELCOME should reject after grant used")
            except crud_promotion.PromoValidationError:
                ok("WELCOME rejected after grant used (expected)")

            order.status = OrderStatus.DELIVERED
            db.commit()
            grant_svc.process_first_delivered_grants(db, user.id)
            thank = (
                db.query(UserPromotionGrant)
                .join(UserPromotionGrant.promotion)
                .filter(
                    UserPromotionGrant.user_id == user.id,
                    UserPromotionGrant.status == GrantStatus.ACTIVE.value,
                )
                .all()
            )
            thank_codes = [
                (g.promotion.code if g.promotion else "?") for g in thank
            ]
            if "THANKYOU188" not in thank_codes:
                fail(f"THANKYOU188 not granted after delivery: {thank_codes}")
            ok(f"THANKYOU188 granted after first delivery")

        # 7. Daily cron (no HTTP — service layer)
        cron_result = run_daily_promotion_cron(db, include_birthday_emails=False)
        if "voucher_grants" not in cron_result:
            fail("Cron missing voucher_grants")
        ok(
            "Cron daily: "
            f"cart={cron_result['voucher_grants']['cart_abandon']} "
            f"comeback={cron_result['voucher_grants']['comeback']} "
            f"backfill={cron_result['voucher_grants']['welcome_backfill']}"
        )

        # 8. HTTP cron if secret configured
        secret = (settings.CRON_SECRET or "").strip()
        if secret:
            try:
                import urllib.request

                url = "http://127.0.0.1:8001/api/v1/promotions/cron/daily-all"
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {secret}"},
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status != 200:
                        fail(f"HTTP cron status {resp.status}")
                    ok(f"HTTP cron /daily-all → {resp.status}")
            except OSError as exc:
                print(f"  SKIP  HTTP cron (backend not on :8001): {exc}")
        else:
            print("  SKIP  HTTP cron — CRON_SECRET not set")

        print("\n=== ALL PASSED ===")

    except Exception as exc:
        errors.append(str(exc))
        print(f"\n=== FAILED: {exc} ===")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
