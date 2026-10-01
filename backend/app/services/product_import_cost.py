"""Giá nhập gốc: tệ lúc cào (hàng Trung Quốc) và giá nhập đồng (hàng Việt Nam).

Không tham gia tính giá bán. Mỗi sản phẩm chỉ được có một trong hai số.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from app.services.ad_spend_profit import stored_cny_price

_CHINA_TOKENS = ("1688", "taobao", "tmall", "vipomall", "pandamall")


def import_cost_is_set(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


def looks_like_china_source(origin: Optional[str], link: Optional[str]) -> bool:
    blob = f"{origin or ''} {link or ''}".lower()
    return any(token in blob for token in _CHINA_TOKENS)


def scraped_cny_amount(raw: Any) -> Optional[float]:
    """Số tệ đã lưu lúc cào. Chuỗi có chữ (nhãn nhóm hàng) không phải giá."""
    parsed = stored_cny_price(raw)
    if parsed is None:
        return None
    if parsed < 0:
        return None
    return float(parsed)


def assert_single_import_cost(
    *,
    existing_cny: Any,
    existing_vnd: Any,
    update_data: dict,
) -> None:
    """Từ chối khi cả giá gốc tệ và giá Việt Nam cùng có số."""
    if "cost_cny" not in update_data and "cost_vnd" not in update_data:
        return
    cny = update_data["cost_cny"] if "cost_cny" in update_data else existing_cny
    vnd = update_data["cost_vnd"] if "cost_vnd" in update_data else existing_vnd
    if import_cost_is_set(cny) and import_cost_is_set(vnd):
        raise HTTPException(
            status_code=400,
            detail="Chỉ điền một cột giá nhập: giá gốc tệ hoặc giá Việt Nam.",
        )


def stamp_scraped_cost_cny(payload: dict) -> None:
    """Ghi giá gốc tệ lúc cào vào payload nếu chưa có giá nhập nào."""
    if not isinstance(payload, dict):
        return
    if import_cost_is_set(payload.get("cost_cny")) or import_cost_is_set(payload.get("cost_vnd")):
        return
    amount = scraped_cny_amount(payload.get("pro_lower_price"))
    if amount is None:
        info = payload.get("product_info")
        market = info.get("market_info") if isinstance(info, dict) else None
        if isinstance(market, dict):
            amount = scraped_cny_amount(market.get("price_cny_low"))
            if amount is None:
                amount = scraped_cny_amount(market.get("source_price"))
    if amount is None:
        return
    origin = payload.get("origin")
    link = payload.get("link_default") or payload.get("source_url")
    if not looks_like_china_source(
        origin if isinstance(origin, str) else None,
        link if isinstance(link, str) else None,
    ):
        return
    payload["cost_cny"] = amount


def cost_cny_backfill_value(
    *,
    origin: Optional[str],
    link: Optional[str],
    pro_lower_price: Any,
    cost_cny: Any,
) -> Optional[float]:
    """Số tệ cần ghi khi ô giá gốc tệ đang trống. None nghĩa là bỏ qua dòng."""
    if import_cost_is_set(cost_cny):
        return None
    if not looks_like_china_source(origin, link):
        return None
    return scraped_cny_amount(pro_lower_price)
