"""
Google Merchant Center — Chiết khấu tự động (Automated discounts).

Xác thực JWT pv2 (ES256) từ URL quảng cáo Mua sắm và khóa giá trên giỏ / checkout.
https://support.google.com/merchants/answer/15152429
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt

from app.core.config import settings

_VN_TZ = timezone(timedelta(hours=7))

# Khoá công khai Google — dùng chung mọi merchant (Automated discounts)
GOOGLE_AUTOMATED_DISCOUNT_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAERUlUpxshr67EO66ZTX0Fpog0LEHc
nUnlSsIrOfroxTLu2XnigBK/lfYRxzQWq9K6nqsSjjYeea0T12r+y3nvqg==
-----END PUBLIC KEY-----"""

CART_LOCK_HOURS = 48


@dataclass(frozen=True)
class GoogleAutomatedDiscountPayload:
    price: float
    prior_price: Optional[float]
    currency: str
    offer_id: str
    merchant_id: str
    expires_at: int


class GoogleAutomatedDiscountError(ValueError):
    pass


def _normalize_offer_id(value: object) -> str:
    return str(value or "").strip()


def _normalize_currency(value: object) -> str:
    return str(value or "").strip().upper()


def _round_price_for_currency(amount: float, currency: str) -> float:
    cur = _normalize_currency(currency)
    if cur == "VND":
        return float(max(0, int(round(amount))))
    return round(max(0.0, amount), 2)


def automated_discount_enabled() -> bool:
    flag = getattr(settings, "GOOGLE_AUTOMATED_DISCOUNT_ENABLED", True)
    if isinstance(flag, str):
        return flag.strip().lower() not in ("0", "false", "no", "off", "disabled")
    return bool(flag)


def verify_google_automated_discount_token(
    token: str,
    *,
    expected_offer_id: Optional[str] = None,
    expected_merchant_id: Optional[str] = None,
) -> GoogleAutomatedDiscountPayload:
    if not automated_discount_enabled():
        raise GoogleAutomatedDiscountError("Tính năng chiết khấu tự động Google chưa được bật.")

    raw = (token or "").strip()
    if not raw:
        raise GoogleAutomatedDiscountError("Thiếu mã thông báo giá (pv2).")

    try:
        header = jwt.get_unverified_header(raw)
    except JWTError as exc:
        raise GoogleAutomatedDiscountError("Mã thông báo giá không hợp lệ.") from exc

    if header.get("alg") != "ES256" or header.get("typ") != "JWT":
        raise GoogleAutomatedDiscountError("Tiêu đề mã thông báo không hợp lệ.")

    try:
        payload = jwt.decode(
            raw,
            GOOGLE_AUTOMATED_DISCOUNT_PUBLIC_KEY_PEM,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise GoogleAutomatedDiscountError("Không xác thực được chữ ký mã thông báo giá.") from exc

    if not isinstance(payload, dict):
        raise GoogleAutomatedDiscountError("Nội dung mã thông báo không hợp lệ.")

    exp = payload.get("exp")
    try:
        exp_i = int(exp)
    except (TypeError, ValueError) as exc:
        raise GoogleAutomatedDiscountError("Mã thông báo thiếu thời hạn hết hạn.") from exc
    if exp_i <= int(datetime.now(timezone.utc).timestamp()):
        raise GoogleAutomatedDiscountError("Mã thông báo giá đã hết hạn.")

    offer_id = _normalize_offer_id(payload.get("o"))
    merchant_id = _normalize_offer_id(payload.get("m"))
    currency = _normalize_currency(payload.get("c") or getattr(settings, "MERCHANT_FEED_CURRENCY", "VND"))

    try:
        price_raw = float(payload.get("p"))
    except (TypeError, ValueError) as exc:
        raise GoogleAutomatedDiscountError("Giá chiết khấu không hợp lệ.") from exc
    if not math.isfinite(price_raw) or price_raw <= 0:
        raise GoogleAutomatedDiscountError("Giá chiết khấu phải lớn hơn 0.")

    prior_price: Optional[float] = None
    if payload.get("pp") is not None:
        try:
            pp = float(payload.get("pp"))
            if math.isfinite(pp) and pp > 0:
                prior_price = pp
        except (TypeError, ValueError):
            prior_price = None

    price = _round_price_for_currency(price_raw, currency)
    if prior_price is not None:
        prior_price = _round_price_for_currency(prior_price, currency)

    expected_offer = _normalize_offer_id(expected_offer_id)
    if expected_offer and offer_id and offer_id != expected_offer:
        raise GoogleAutomatedDiscountError("Mã sản phẩm trong mã thông báo không khớp.")

    configured_merchant = _normalize_offer_id(
        expected_merchant_id or getattr(settings, "GOOGLE_MERCHANT_CENTER_ID", "")
    )
    if configured_merchant and merchant_id and merchant_id != configured_merchant:
        raise GoogleAutomatedDiscountError("Mã người bán trong mã thông báo không khớp.")

    feed_currency = _normalize_currency(getattr(settings, "MERCHANT_FEED_CURRENCY", "VND"))
    if feed_currency and currency and currency != feed_currency:
        raise GoogleAutomatedDiscountError("Đơn vị tiền tệ không khớp với feed Merchant Center.")

    return GoogleAutomatedDiscountPayload(
        price=price,
        prior_price=prior_price,
        currency=currency,
        offer_id=offer_id,
        merchant_id=merchant_id,
        expires_at=exp_i,
    )


def google_discount_lock_until(*, jwt_expires_at: int) -> datetime:
    jwt_dt = datetime.fromtimestamp(jwt_expires_at, tz=timezone.utc)
    cart_cap = datetime.now(timezone.utc) + timedelta(hours=CART_LOCK_HOURS)
    locked = min(jwt_dt, cart_cap)
    return locked.astimezone(_VN_TZ)


def build_google_discount_product_data(
    payload: GoogleAutomatedDiscountPayload,
) -> dict[str, Any]:
    locked = google_discount_lock_until(jwt_expires_at=payload.expires_at)
    return {
        "price": payload.price,
        "prior_price": payload.prior_price,
        "currency": payload.currency,
        "offer_id": payload.offer_id,
        "merchant_id": payload.merchant_id,
        "locked_until": locked.isoformat(),
        "source": "google_automated_discount",
    }


def read_google_discount_lock(product_data: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(product_data, dict):
        return None
    block = product_data.get("google_automated_discount")
    if not isinstance(block, dict):
        return None
    locked_until = block.get("locked_until")
    if not locked_until:
        return None
    try:
        locked_dt = datetime.fromisoformat(str(locked_until))
    except ValueError:
        return None
    if locked_dt.tzinfo is None:
        locked_dt = locked_dt.replace(tzinfo=_VN_TZ)
    if locked_dt <= datetime.now(_VN_TZ):
        return None
    try:
        price = float(block.get("price"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0:
        return None
    prior: Optional[float] = None
    if block.get("prior_price") is not None:
        try:
            pp = float(block.get("prior_price"))
            if math.isfinite(pp) and pp > 0:
                prior = pp
        except (TypeError, ValueError):
            prior = None
    return {
        "price": price,
        "prior_price": prior,
        "offer_id": _normalize_offer_id(block.get("offer_id")),
        "locked_until": locked_dt.isoformat(),
    }


def apply_google_discount_to_cart_line(
    *,
    product,
    unit_sale: float,
    list_original: float,
    product_data: dict[str, Any],
    google_pv2_token: Optional[str] = None,
) -> tuple[float, float, dict[str, Any]]:
    """Áp giá chiết khấu Google nếu token hợp lệ hoặc khóa giá còn hiệu lực."""
    pd = dict(product_data or {})
    existing = read_google_discount_lock(pd)
    if existing:
        list_price = float(existing.get("prior_price") or list_original or unit_sale)
        return float(existing["price"]), list_price, pd

    token = (google_pv2_token or pd.get("google_pv2_token") or "").strip()
    if not token:
        return unit_sale, list_original, pd

    payload = verify_google_automated_discount_token(
        token,
        expected_offer_id=getattr(product, "product_id", None),
    )
    block = build_google_discount_product_data(payload)
    pd["google_automated_discount"] = block
    pd.pop("google_pv2_token", None)
    list_price = float(payload.prior_price or list_original or unit_sale)
    return float(payload.price), list_price, pd
