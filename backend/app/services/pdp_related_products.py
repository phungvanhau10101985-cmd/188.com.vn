"""
Gom SP liên quan PDP — một session DB, tối đa 2 listing query (main + shop group).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy.orm import Session

from app import crud

PdpRelatedTab = Literal["bestselling", "same_price", "lower_price", "higher_price"]
PRICE_BAND_VND = 300_000
DEFAULT_LIMIT = 20


def _excel_cell(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def _floor_price_vnd(value: Any) -> Optional[int]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not v or v <= 0:
        return None
    return int(v)


def _price_band_lower(cur: int) -> Optional[Tuple[int, int]]:
    max_price = cur - 1
    if max_price < 0:
        return None
    min_price = max(0, cur - PRICE_BAND_VND)
    if min_price > max_price:
        return None
    return min_price, max_price


def _price_band_higher(cur: int) -> Tuple[int, int]:
    return cur + 1, cur + PRICE_BAND_VND


def listing_params_same_chinese_shop_cat2(product) -> Optional[Dict[str, str]]:
    sub2 = _excel_cell(getattr(product, "subcategory", None))
    sc = _excel_cell(getattr(product, "shop_name_chinese", None))
    if not sub2 or not sc:
        return None
    out: Dict[str, str] = {"subcategory": sub2, "shop_name_chinese": sc}
    cat = _excel_cell(getattr(product, "category", None))
    if cat:
        out["category"] = cat
    return out


def listing_params_for_price_sibling_tab(
    tab: Literal["lower_price", "higher_price"],
    product,
) -> Optional[Dict[str, Any]]:
    sub2 = _excel_cell(getattr(product, "subcategory", None))
    cur = _floor_price_vnd(getattr(product, "price", None))
    if not sub2 or cur is None:
        return None
    cat = _excel_cell(getattr(product, "category", None))
    base: Dict[str, Any] = {"subcategory": sub2}
    if cat:
        base["category"] = cat
    if tab == "lower_price":
        band = _price_band_lower(cur)
        if not band:
            return None
        base["min_price"], base["max_price"] = band
        return base
    base["min_price"], base["max_price"] = _price_band_higher(cur)
    return base


def build_related_list_kwargs(
    product,
    tab: PdpRelatedTab,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    """
    Trả (kwargs cho get_products, sort_purchases_desc).
    None → không có plan main (chỉ shop group nếu bestselling).
    """
    base: Dict[str, Any] = {
        "skip": 0,
        "limit": limit,
        "is_active": True,
        "skip_total": True,
    }

    if tab == "bestselling":
        st = _excel_cell(getattr(product, "style", None))
        if st:
            return {**base, "style": st, "sort": "purchases_desc"}, True
        sub2 = _excel_cell(getattr(product, "subcategory", None))
        if sub2:
            kw = {**base, "subcategory": sub2, "sort": "purchases_desc"}
            cat = _excel_cell(getattr(product, "category", None))
            if cat:
                kw["category"] = cat
            return kw, True
        return None, False

    if tab == "same_price":
        sibling = listing_params_same_chinese_shop_cat2(product)
        if not sibling:
            return None, False
        return {**base, **sibling}, False

    if tab in ("lower_price", "higher_price"):
        sibling = listing_params_for_price_sibling_tab(tab, product)
        if not sibling:
            return None, False
        return {**base, **sibling}, False

    return None, False


def _fetch_listing(db: Session, kwargs: Dict[str, Any]) -> List[Any]:
    result = crud.product.get_products(db, **kwargs)
    products = result.get("products") if isinstance(result, dict) else None
    return list(products or [])


def fetch_pdp_related_rows(
    db: Session,
    product,
    tab: PdpRelatedTab,
    *,
    limit: int = DEFAULT_LIMIT,
) -> Tuple[List[Any], List[Any]]:
    """Trả (related_rows, shop_group_rows) — đã loại SP hiện tại."""
    current_id = int(getattr(product, "id", 0) or 0)
    main_kw, _ = build_related_list_kwargs(product, tab, limit=limit)
    shop_kw = listing_params_same_chinese_shop_cat2(product)

    related_rows: List[Any] = []
    shop_rows: List[Any] = []

    if main_kw:
        related_rows = _fetch_listing(db, main_kw)

    if tab == "bestselling" and shop_kw:
        shop_rows = _fetch_listing(
            db,
            {
                "skip": 0,
                "limit": limit,
                "is_active": True,
                "skip_total": True,
                "sort": "purchases_desc",
                **shop_kw,
            },
        )
    elif not main_kw and tab == "bestselling" and shop_kw:
        shop_rows = _fetch_listing(
            db,
            {
                "skip": 0,
                "limit": limit,
                "is_active": True,
                "skip_total": True,
                "sort": "purchases_desc",
                **shop_kw,
            },
        )

    def _filter_current(rows: List[Any]) -> List[Any]:
        return [r for r in rows if int(getattr(r, "id", 0) or 0) != current_id]

    return _filter_current(related_rows), _filter_current(shop_rows)
