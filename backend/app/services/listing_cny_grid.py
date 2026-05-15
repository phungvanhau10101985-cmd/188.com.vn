"""
Quy đổi CN¥ → VNĐ theo **hệ số lưới IF** + **tỷ giá** — khớp `frontend/lib/taobao-cards-html-parse.ts`
(`cnyExchangeMultiplierFromGrid`, `estimateListingVndRounded`, `DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE`).
~VNĐ = CN¥ × hệ_số × tỷ_giá (Decimal), làm tròn số học (`ROUND_HALF_UP` về nguyên), rồi **làm tròn lên** bội số `LISTING_VND_PRICE_CEILING_STEP` (10.000 ₫).
Khớp `estimateListingVndRounded` trong `taobao-cards-html-parse.ts`.

Khi chỉnh thang nhân hoặc tỷ giá mặc định nên đổi đồng bộ hai nơi (hoặc `LISTING_IMPORT_VND_PER_CNY` trong .env backend).
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Optional

# Khớp `DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE` trong taobao-cards-html-parse.ts
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_VND_PER_CNY_FOR_LISTING_ESTIMATE = 3580.0

# Bội số VNĐ sau quy đổi (làm tròn lên). Ví dụ 1.192.856 → 1.200.000.
LISTING_VND_PRICE_CEILING_STEP = 10_000


def cny_exchange_multiplier_from_grid(cny_price: float) -> Decimal:
    """Hệ số nhân theo giá nhân dân tệ — literal Decimal (không `str(float)`). Khớp bậc IF trong file TS."""
    try:
        j = float(cny_price)
    except (TypeError, ValueError):
        return Decimal("0")
    if not math.isfinite(j) or j <= 0:
        return Decimal("0")
    if j <= 90:
        return Decimal("3")
    if j <= 100:
        return Decimal("2.9")
    if j <= 120:
        return Decimal("2.8")
    if j <= 140:
        return Decimal("2.7")
    if j <= 160:
        return Decimal("2.6")
    if j <= 180:
        return Decimal("2.6")
    if j <= 200:
        return Decimal("2.6")
    if j <= 240:
        return Decimal("2.6")
    if j <= 280:
        return Decimal("2.6")
    if j <= 320:
        return Decimal("2.5")
    if j <= 370:
        return Decimal("2.5")
    if j <= 400:
        return Decimal("2.5")
    return Decimal("2.5")


def estimate_listing_vnd_rounded(
    price_cny: float,
    coef: Decimal,
    vnd_per_one_cny: float,
) -> Optional[int]:
    """CN¥ × hệ_số × (VNĐ / 1 CN¥), làm tròn nguyên `ROUND_HALF_UP`, rồi làm tròn lên bội `LISTING_VND_PRICE_CEILING_STEP`."""
    try:
        dcny = Decimal(str(price_cny)).normalize()
        dr = Decimal(str(vnd_per_one_cny)).normalize()
    except Exception:
        return None
    if (
        not math.isfinite(float(price_cny))
        or float(price_cny) <= 0
        or coef <= 0
        or not math.isfinite(float(vnd_per_one_cny))
        or float(vnd_per_one_cny) <= 0
    ):
        return None
    total = dcny * coef * dr
    try:
        rounded_int = int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return None
    step = LISTING_VND_PRICE_CEILING_STEP
    try:
        return int(math.ceil(rounded_int / step) * step)
    except Exception:
        return None


def parse_approx_cny_amount_from_cell(val: Any) -> Optional[float]:
    """
    Suy ~CN¥ từ ô Excel: số thuần, hoặc chuỗi có ¥/￥/元 (khớp ý parseApproxCnyAmountFromPriceRaw).
    """
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        try:
            f = float(val)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) and 0 < f <= 999_999_999 else None

    flat = unicodedata.normalize("NFKC", str(val)).replace("\u00a0", "").strip()
    if not re.search(r"[0-9]", flat):
        return None
    canon = re.sub(r"\s+", "", flat)
    canon = re.sub(r"¥|￥|元", "", canon, flags=re.I)
    trimmed = re.sub(r"^[^\d]+", "", canon)
    if not re.search(r"[0-9]", trimmed):
        return None

    decimal_tok = re.match(r"^(\d{1,11}[.,]\d{1,7})(?!\d)", trimmed)
    if decimal_tok:
        token_str = decimal_tok.group(1)
    else:
        m_int = re.match(r"^(\d{1,11})", trimmed)
        token_str = m_int.group(1) if m_int else None
    if not token_str:
        return None

    token = token_str.replace(",", ".")
    token = re.sub(r"^0+(\d)", r"\1", token)
    if token.count(".") > 1:
        token = token.replace(".", "")
    try:
        n = float(token)
    except ValueError:
        return None
    if not math.isfinite(n) or n <= 0 or n > 999_999_999:
        return None
    return n
