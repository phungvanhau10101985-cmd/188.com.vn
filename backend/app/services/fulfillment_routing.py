"""Chuẩn hóa nguồn hàng và phân tuyến fulfillment tại thời điểm checkout."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse
from decimal import Decimal


FULFILLMENT_CHINA = "china"
FULFILLMENT_VIETNAM = "vietnam"

SOURCE_1688 = "1688"
SOURCE_TAOBAO = "taobao"
SOURCE_TMALL = "tmall"

_CHINA_HOST_SUFFIXES = {
    SOURCE_1688: "1688.com",
    SOURCE_TAOBAO: "taobao.com",
    SOURCE_TMALL: "tmall.com",
}


def normalized_source_hostname(source_url: Optional[str]) -> str:
    raw = (source_url or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        return (urlparse(candidate).hostname or "").strip(".").lower()
    except ValueError:
        return ""


def source_platform_from_url(source_url: Optional[str]) -> Optional[str]:
    """Chỉ nhận host thật hoặc subdomain của 1688/Taobao/Tmall."""
    host = normalized_source_hostname(source_url)
    for platform, suffix in _CHINA_HOST_SUFFIXES.items():
        if host == suffix or host.endswith(f".{suffix}"):
            return platform
    return None


def fulfillment_source_from_url(source_url: Optional[str]) -> str:
    return FULFILLMENT_CHINA if source_platform_from_url(source_url) else FULFILLMENT_VIETNAM


def classify_legacy_item_source(
    *,
    snapshot_url: Optional[str],
    product_url: Optional[str],
    product_exists: bool,
    snapshot_source: Optional[str] = None,
) -> tuple[str, Optional[str], bool]:
    """Không đoán TQ khi mất dữ liệu; link trống của product còn tồn tại là hàng VN."""
    resolved_url = (snapshot_url or "").strip()
    if not resolved_url and product_exists:
        resolved_url = (product_url or "").strip()
    if not resolved_url and not product_exists:
        source = (snapshot_source or "").strip().lower()
        if source not in (FULFILLMENT_CHINA, FULFILLMENT_VIETNAM):
            source = FULFILLMENT_VIETNAM
        return source, None, True
    return fulfillment_source_from_url(resolved_url), resolved_url or None, False


def allocate_decimal_total(
    total: Decimal,
    weights: dict[str, Decimal],
    ordered_keys: list[str],
) -> dict[str, Decimal]:
    """Phân bổ tiền theo tỷ trọng và dồn sai số làm tròn vào nhóm cuối."""
    result: dict[str, Decimal] = {}
    left = Decimal(total)
    weight_total = sum((max(Decimal("0"), weights.get(key, Decimal("0"))) for key in ordered_keys), Decimal("0"))
    for index, key in enumerate(ordered_keys):
        if index == len(ordered_keys) - 1:
            amount = left
        elif weight_total > 0:
            amount = (
                Decimal(total)
                * max(Decimal("0"), weights.get(key, Decimal("0")))
                / weight_total
            ).quantize(Decimal("0.01"))
        else:
            amount = Decimal("0")
        amount = max(Decimal("0"), min(amount, left))
        result[key] = amount
        left -= amount
    return result

