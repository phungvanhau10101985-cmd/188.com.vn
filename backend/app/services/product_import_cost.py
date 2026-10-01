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
        amount = float(value)
    except (TypeError, ValueError):
        return False
    if amount != amount:  # NaN
        return False
    return amount >= 0


def parse_excel_import_cost(value: Any) -> Optional[float]:
    """Ô giá nhập trên Excel. Trống → None. Âm hoặc không phải số → ValueError."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        if value < 0:
            raise ValueError("Giá nhập không được âm")
        return float(value)
    if isinstance(value, int):
        if value < 0:
            raise ValueError("Giá nhập không được âm")
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return None
    compact = text.replace(" ", "").replace("₫", "").replace("đ", "").replace("¥", "")
    if "," in compact and "." in compact:
        compact = compact.replace(",", "")
    elif "," in compact:
        tail = compact.split(",")[-1]
        compact = compact.replace(",", "") if len(tail) == 3 else compact.replace(",", ".")
    try:
        amount = float(compact)
    except (TypeError, ValueError) as exc:
        raise ValueError("Giá nhập không đọc được") from exc
    if amount != amount or amount in (float("inf"), float("-inf")):
        return None
    if amount < 0:
        raise ValueError("Giá nhập không được âm")
    return amount


_EXCEL_COST_CNY_KEYS = ("cost_cny", "Giá gốc tệ", "Gia goc te")
_EXCEL_COST_VND_KEYS = ("cost_vnd", "Giá Việt Nam", "Gia Viet Nam")


def _excel_row_key(row: dict, keys: tuple[str, ...]) -> Optional[str]:
    folded = {str(col).strip().casefold(): col for col in row.keys() if col is not None}
    for key in keys:
        if key in row:
            return key
        found = folded.get(key.strip().casefold())
        if found is not None:
            return str(found)
    return None


def excel_row_import_costs(row: dict) -> dict:
    """
    Đọc hai cột giá nhập nếu file có chúng.
    Cột thiếu thì không trả key — import không xóa giá đang lưu.
    Ô trống → None. Cả hai ô đều có số thì từ chối.
    """
    if not isinstance(row, dict):
        return {}
    cny_key = _excel_row_key(row, _EXCEL_COST_CNY_KEYS)
    vnd_key = _excel_row_key(row, _EXCEL_COST_VND_KEYS)
    if cny_key is None and vnd_key is None:
        return {}
    out: dict = {}
    if cny_key is not None:
        out["cost_cny"] = parse_excel_import_cost(row.get(cny_key))
    if vnd_key is not None:
        out["cost_vnd"] = parse_excel_import_cost(row.get(vnd_key))
    if import_cost_is_set(out.get("cost_cny")) and import_cost_is_set(out.get("cost_vnd")):
        raise ValueError("Chỉ điền một cột giá nhập: giá gốc tệ hoặc giá Việt Nam.")
    return out


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
