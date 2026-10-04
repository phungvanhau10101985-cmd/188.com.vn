"""Giá bán / giá tệ / mã của đúng màu hoặc cặp màu-size đã lưu trên sản phẩm."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.models.product import Product


def _as_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def color_label_at(colors: List[Any], index: int) -> str:
    """Khớp `colorLabelForCart` trên frontend."""
    if index < 0 or index >= len(colors):
        return ""
    entry = colors[index]
    if not isinstance(entry, dict):
        return ""
    name = str(entry.get("name") or "").strip()
    base = name or "Màu"
    dup = sum(1 for item in colors if isinstance(item, dict) and str(item.get("name") or "").strip() == name)
    if dup > 1 or not name:
        return f"{base} ({index + 1})"
    return base


def _color_index(colors: List[Any], selected_color: Optional[str]) -> int:
    sel = (selected_color or "").strip()
    if not sel or not colors:
        return -1
    for i in range(len(colors)):
        if color_label_at(colors, i) == sel:
            return i
    for i, entry in enumerate(colors):
        if not isinstance(entry, dict):
            continue
        for key in ("name", "value", "sku", "sku_code"):
            if str(entry.get(key) or "").strip() == sel:
                return i
    match = re.search(r"\((\d+)\)\s*$", sel)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(colors):
            return idx
    return -1


def _pairs(product: Product) -> List[Dict[str, Any]]:
    info = product.product_info if isinstance(product.product_info, dict) else {}
    variants = info.get("variants") if isinstance(info.get("variants"), dict) else {}
    pairs = _as_dict_list(variants.get("pairs"))
    if pairs:
        return pairs
    return _as_dict_list(variants.get("price_pairs"))


def _positive(raw: Any) -> Optional[float]:
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val > 0:
        return val
    return None


def resolve_variant_quote(
    product: Product,
    selected_color: Optional[str],
    selected_size: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Bản ghi biến thể khách chọn: price (VNĐ bán), price_cny, sku_code, img, name.
    Không có giá theo mã thì None — caller dùng giá sản phẩm.
    """
    colors = _as_dict_list(product.colors)
    idx = _color_index(colors, selected_color)
    color = colors[idx] if idx >= 0 else None
    color_name = ""
    if color is not None:
        color_name = color_label_at(colors, idx) or str(color.get("name") or "").strip()
    size = (selected_size or "").strip()
    if color_name and size:
        for pair in _pairs(product):
            pair_color = str(pair.get("color") or "").strip()
            pair_size = str(pair.get("size") or "").strip()
            if pair_size != size:
                continue
            if pair_color not in {color_name, str(color.get("name") or "").strip() if color else ""}:
                continue
            price = _positive(pair.get("price"))
            if price is None:
                continue
            return {
                "price": price,
                "price_cny": _positive(pair.get("price_cny")),
                "sku_code": str(pair.get("sku_code") or pair.get("sku") or "").strip()[:100],
                "img": str(pair.get("img") or "").strip(),
                "name": color_name,
            }
    if color is not None:
        price = _positive(color.get("price"))
        if price is not None:
            return {
                "price": price,
                "price_cny": _positive(color.get("price_cny")),
                "sku_code": str(color.get("sku_code") or color.get("sku") or "").strip()[:100],
                "img": str(color.get("img") or color.get("image") or "").strip(),
                "name": color_name,
            }
    return None


def selected_color_name_for_line(
    product: Any,
    selected_color: Optional[str],
    selected_size: Optional[str],
    current_name: Optional[str],
) -> Optional[str]:
    """Tên màu đã lưu. Client gửi thì giữ; trống thì lấy từ quote của mã đang chọn."""
    current = (current_name or "").strip()
    if current:
        return current
    quote = resolve_variant_quote(product, selected_color, selected_size)
    if not quote:
        return None
    name = str(quote.get("name") or "").strip()
    return name or None
