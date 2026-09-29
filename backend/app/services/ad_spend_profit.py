"""Hạch toán lợi nhuận đơn đã cọc trên trang chi phí quảng cáo.

Lợi nhuận = giá bán − (giá hàng ¥ + ship TQ ¥ + ship cửa khẩu ¥) × tỷ giá − ship Hà Nội − quảng cáo.
Quảng cáo trừ một lần ở tổng kỳ, không chia vào từng đơn.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.ad_spend import AdSpendOrderCost, AdSpendSettings
from app.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.models.product import Product
from app.services.listing_cny_grid import listing_vnd_to_cny, parse_approx_cny_amount_from_cell

_VN_TZ = timezone(timedelta(hours=7))
MAX_PROFIT_ORDERS = 400
_MONEY = Decimal("0.01")
_RATE = Decimal("0.0001")
_HAS_LETTER = re.compile(r"[A-Za-z]")


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if not number.is_finite():
        return None
    return number


def _money(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value.quantize(_MONEY, rounding=ROUND_HALF_UP))


def _rate_out(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value.quantize(_RATE, rounding=ROUND_HALF_UP))


def default_listing_rate() -> Decimal:
    from app.core.config import settings

    raw = getattr(settings, "LISTING_IMPORT_VND_PER_CNY", None) or 3580
    parsed = _dec(raw)
    if parsed is None or parsed <= 0:
        return Decimal("3580")
    return parsed


def stored_cny_price(raw: Any) -> Optional[float]:
    """Giá tệ đã lưu (số, «146,00», «20¥»). Nhãn nhóm hàng có chữ — ví dụ «giày tây nam g05» — không phải số tệ."""
    if isinstance(raw, str) and _HAS_LETTER.search(raw):
        return None
    return parse_approx_cny_amount_from_cell(raw)


def goods_cny_from_lines(lines: Sequence[Tuple[Any, Any]]) -> Optional[Decimal]:
    """Tổng giá hàng ¥ = số lượng × giá tệ trên sản phẩm. Thiếu một dòng thì không suy ra 0."""
    if not lines:
        return None
    total = Decimal("0")
    for quantity, raw_price in lines:
        parsed = stored_cny_price(raw_price)
        if parsed is None:
            return None
        qty = _dec(quantity)
        if qty is None or qty <= 0:
            return None
        total += Decimal(str(parsed)) * qty
    return total


def line_listing_cny(
    quantity: Any,
    unit_vnd: Any,
    catalog_raw: Any,
    vnd_per_cny: Optional[Decimal],
    line_total_vnd: Any = None,
) -> Optional[Decimal]:
    """Giá tệ một dòng: ưu tiên số đã lưu lúc cào, không có thì đảo đơn giá hoặc thành tiền dòng."""
    if vnd_per_cny is None or vnd_per_cny <= 0:
        return None
    qty = _dec(quantity)
    catalog = stored_cny_price(catalog_raw)
    if catalog is not None and qty is not None and qty > 0:
        return Decimal(str(catalog)) * qty
    unit = _dec(unit_vnd)
    if unit is not None and unit > 0 and qty is not None and qty > 0:
        inverted = listing_vnd_to_cny(float(unit), float(vnd_per_cny))
        if inverted is not None:
            return Decimal(str(inverted)) * qty
    total = _dec(line_total_vnd)
    if total is not None and total > 0:
        inverted = listing_vnd_to_cny(float(total), float(vnd_per_cny))
        if inverted is not None:
            return Decimal(str(inverted))
    return None


def invert_merchandise_cny(merchandise_vnd: Any, vnd_per_cny: Optional[Decimal]) -> Optional[Decimal]:
    amount = _dec(merchandise_vnd)
    if amount is None or amount <= 0 or vnd_per_cny is None or vnd_per_cny <= 0:
        return None
    inverted = listing_vnd_to_cny(float(amount), float(vnd_per_cny))
    if inverted is None:
        return None
    return Decimal(str(inverted))


def goods_cny_matching_listing(
    lines: Sequence[Tuple[Any, ...]],
    vnd_per_cny: Optional[Decimal],
    merchandise_vnd: Any = None,
) -> Optional[Decimal]:
    """Cộng giá tệ từng dòng. Dòng nào không đảo được thì lấy giá hàng của cả đơn (không gồm phí ship khách trả)."""
    if lines:
        parts: List[Decimal] = []
        for row in lines:
            quantity, unit_vnd, catalog_raw = row[0], row[1], row[2]
            line_total = row[3] if len(row) > 3 else None
            part = line_listing_cny(quantity, unit_vnd, catalog_raw, vnd_per_cny, line_total)
            if part is None:
                parts = []
                break
            parts.append(part)
        if parts:
            return sum(parts, Decimal("0"))
    return invert_merchandise_cny(merchandise_vnd, vnd_per_cny)


def order_cost_vnd(
    *,
    goods_cny: Optional[Decimal],
    ship_china_cny: Decimal,
    ship_border_cny: Decimal,
    ship_hanoi_vnd: Decimal,
    vnd_per_cny: Optional[Decimal],
) -> Optional[Decimal]:
    if goods_cny is None or vnd_per_cny is None or vnd_per_cny <= 0:
        return None
    cny = goods_cny + ship_china_cny + ship_border_cny
    return cny * vnd_per_cny + ship_hanoi_vnd


def revenue_to_cny(goods_cny: Optional[Decimal]) -> Optional[Decimal]:
    """Giá hàng quy ra tệ — tổng CN¥ đã cào hoặc đã đảo theo lưới, không chia doanh thu cho tỷ giá."""
    return goods_cny


def period_profit(
    *,
    revenue_vnd: Decimal,
    cost_vnd: Optional[Decimal],
    ad_spend_vnd: Optional[Decimal],
) -> Optional[Decimal]:
    if cost_vnd is None or ad_spend_vnd is None:
        return None
    return revenue_vnd - cost_vnd - ad_spend_vnd


def _non_negative(value: Any, label: str) -> Decimal:
    number = _dec(value)
    if number is None:
        raise ValueError(f"{label} không hợp lệ.")
    if number < 0:
        raise ValueError(f"{label} không được âm.")
    return number


def _optional_non_negative(value: Any, label: str) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    return _non_negative(value, label)


def _vn_day(moment: Optional[datetime]) -> Optional[str]:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_VN_TZ)
    return moment.astimezone(_VN_TZ).date().isoformat()


def _deposited_clause():
    return (
        Order.status != OrderStatus.CANCELLED.value,
        Order.payment_status != PaymentStatus.REFUNDED.value,
        (
            (Order.deposit_paid > 0)
            | (Order.deposit_paid_at.isnot(None))
            | (Order.payment_status == PaymentStatus.DEPOSIT_PAID.value)
            | (Order.status == OrderStatus.DEPOSIT_PAID.value)
        ),
    )


def load_profit_sheet(db: Session, date_from: str, date_to: str) -> dict:
    from sqlalchemy import func

    from app.crud.order import resolve_order_stats_range
    from app.services.ad_spend_service import get_or_create_settings

    start_dt, end_dt, _label, iso_from, iso_to = resolve_order_stats_range(
        date_from=date_from,
        date_to=date_to,
    )
    if start_dt is None or end_dt is None or not iso_from or not iso_to:
        raise ValueError("Chọn khoảng ngày để hạch toán.")

    settings_row = get_or_create_settings(db)
    saved_rate = _dec(settings_row.vnd_per_cny)
    rate = saved_rate if saved_rate is not None and saved_rate > 0 else default_listing_rate()
    ship_china_default = _dec(settings_row.ship_china_domestic_cny) or Decimal("0")
    ship_border_default = _dec(settings_row.ship_border_to_hanoi_cny) or Decimal("0")
    ship_hanoi_default = _dec(settings_row.ship_hanoi_to_customer_vnd) or Decimal("0")

    when = func.coalesce(Order.deposit_paid_at, Order.created_at)
    orders = (
        db.query(Order)
        .filter(*_deposited_clause(), when >= start_dt, when <= end_dt)
        .order_by(when.desc(), Order.id.desc())
        .limit(MAX_PROFIT_ORDERS + 1)
        .all()
    )
    truncated = len(orders) > MAX_PROFIT_ORDERS
    orders = orders[:MAX_PROFIT_ORDERS]
    order_ids = [order.id for order in orders]

    lines_by_order: Dict[int, List[Tuple[Any, Any, Any, Any]]] = {order_id: [] for order_id in order_ids}
    if order_ids:
        item_rows = (
            db.query(
                OrderItem.order_id,
                OrderItem.quantity,
                OrderItem.unit_price,
                OrderItem.price,
                OrderItem.total_price,
                Product.pro_lower_price,
            )
            .outerjoin(Product, Product.id == OrderItem.product_id)
            .filter(OrderItem.order_id.in_(order_ids))
            .all()
        )
        for order_id, quantity, unit_price, legacy_price, line_total, raw_price in item_rows:
            unit = unit_price if unit_price not in (None, 0) else legacy_price
            lines_by_order.setdefault(int(order_id), []).append((quantity, unit, raw_price, line_total))

    overrides = {}
    if order_ids:
        for row in db.query(AdSpendOrderCost).filter(AdSpendOrderCost.order_id.in_(order_ids)).all():
            overrides[row.order_id] = row

    payload_orders: List[dict] = []
    revenue_total = Decimal("0")
    cost_total = Decimal("0")
    cost_complete = True
    missing_goods = 0
    for order in orders:
        revenue = _dec(order.total_amount) or Decimal("0")
        revenue_total += revenue
        order_lines = lines_by_order.get(order.id) or []
        goods_vnd = _dec(order.subtotal)
        if goods_vnd is None or goods_vnd <= 0:
            shipping = _dec(order.shipping_fee) or Decimal("0")
            goods_vnd = revenue - shipping if revenue > shipping else revenue
        catalog = goods_cny_matching_listing(order_lines, rate, goods_vnd)
        override = overrides.get(order.id)
        goods_override = _dec(override.goods_cny) if override is not None else None
        ship_china_override = _dec(override.ship_china_domestic_cny) if override is not None else None
        ship_border_override = _dec(override.ship_border_to_hanoi_cny) if override is not None else None
        ship_hanoi_override = _dec(override.ship_hanoi_to_customer_vnd) if override is not None else None
        goods = goods_override if goods_override is not None else catalog
        ship_china = ship_china_override if ship_china_override is not None else ship_china_default
        ship_border = ship_border_override if ship_border_override is not None else ship_border_default
        ship_hanoi = ship_hanoi_override if ship_hanoi_override is not None else ship_hanoi_default
        cost = order_cost_vnd(
            goods_cny=goods,
            ship_china_cny=ship_china,
            ship_border_cny=ship_border,
            ship_hanoi_vnd=ship_hanoi,
            vnd_per_cny=rate,
        )
        if cost is None:
            cost_complete = False
            missing_goods += 1
        else:
            cost_total += cost
        deposited = order.deposit_paid_at or order.created_at
        payload_orders.append(
            {
                "order_id": order.id,
                "order_code": order.order_code,
                "deposited_on": _vn_day(deposited),
                "revenue_vnd": _money(revenue) or 0,
                "merchandise_vnd": _money(goods_vnd) or 0,
                "catalog_goods_cny": _money(catalog),
                "lines": [
                    {
                        "quantity": int(quantity or 0),
                        "unit_price_vnd": _money(_dec(unit)) or 0,
                        "line_total_vnd": _money(_dec(line_total)) or 0,
                        "catalog_cny": _money(_dec(str(parsed))) if (parsed := stored_cny_price(raw)) is not None else None,
                    }
                    for quantity, unit, raw, line_total in order_lines
                ],
                "goods_cny_override": _money(goods_override),
                "ship_china_domestic_cny_override": _money(ship_china_override),
                "ship_border_to_hanoi_cny_override": _money(ship_border_override),
                "ship_hanoi_to_customer_vnd_override": _money(ship_hanoi_override),
                "cost_vnd": _money(cost),
                "gross_profit_vnd": _money(revenue - cost) if cost is not None else None,
            }
        )

    goods_total = Decimal("0")
    goods_complete = True
    for item in payload_orders:
        if item["goods_cny_override"] is not None:
            goods_total += Decimal(str(item["goods_cny_override"]))
        elif item["catalog_goods_cny"] is not None:
            goods_total += Decimal(str(item["catalog_goods_cny"]))
        else:
            goods_complete = False
    revenue_cny = revenue_to_cny(goods_total if goods_complete else None)
    return {
        "date_from": iso_from,
        "date_to": iso_to,
        "vnd_per_cny": _rate_out(rate) or 0,
        "vnd_per_cny_saved": saved_rate is not None and saved_rate > 0,
        "ship_china_domestic_cny": _money(ship_china_default) or 0,
        "ship_border_to_hanoi_cny": _money(ship_border_default) or 0,
        "ship_hanoi_to_customer_vnd": _money(ship_hanoi_default) or 0,
        "order_count": len(payload_orders),
        "truncated": truncated,
        "missing_goods_count": missing_goods,
        "revenue_vnd": _money(revenue_total) or 0,
        "revenue_cny": _money(revenue_cny),
        "cost_vnd": _money(cost_total) if cost_complete else None,
        "orders": payload_orders,
    }


def save_profit_inputs(db: Session, payload: dict) -> None:
    from app.services.ad_spend_service import get_or_create_settings

    rate = _non_negative(payload.get("vnd_per_cny"), "Tỷ giá")
    if rate <= 0:
        raise ValueError("Tỷ giá phải lớn hơn 0.")
    ship_china = _non_negative(payload.get("ship_china_domestic_cny") or 0, "Ship Trung Quốc nội địa")
    ship_border = _non_negative(payload.get("ship_border_to_hanoi_cny") or 0, "Ship cửa khẩu về Hà Nội")
    ship_hanoi = _non_negative(payload.get("ship_hanoi_to_customer_vnd") or 0, "Ship Hà Nội đến khách")

    row = get_or_create_settings(db)
    row.vnd_per_cny = rate
    row.ship_china_domestic_cny = ship_china
    row.ship_border_to_hanoi_cny = ship_border
    row.ship_hanoi_to_customer_vnd = ship_hanoi

    orders = payload.get("orders") or []
    if len(orders) > MAX_PROFIT_ORDERS:
        raise ValueError("Quá nhiều đơn để lưu một lúc.")
    order_ids = []
    for item in orders:
        order_id = item.get("order_id")
        if not isinstance(order_id, int) or order_id <= 0:
            raise ValueError("Mã đơn không hợp lệ.")
        order_ids.append(order_id)
    if len(set(order_ids)) != len(order_ids):
        raise ValueError("Danh sách đơn bị trùng.")
    if order_ids:
        found = {item_id for (item_id,) in db.query(Order.id).filter(Order.id.in_(order_ids)).all()}
        if found != set(order_ids):
            raise ValueError("Có đơn không tồn tại.")
        existing = {
            item.order_id: item
            for item in db.query(AdSpendOrderCost).filter(AdSpendOrderCost.order_id.in_(order_ids)).all()
        }
        for item in orders:
            goods = _optional_non_negative(item.get("goods_cny"), "Giá hàng tệ")
            china = _optional_non_negative(item.get("ship_china_domestic_cny"), "Ship Trung Quốc nội địa")
            border = _optional_non_negative(item.get("ship_border_to_hanoi_cny"), "Ship cửa khẩu về Hà Nội")
            hanoi = _optional_non_negative(item.get("ship_hanoi_to_customer_vnd"), "Ship Hà Nội đến khách")
            current = existing.get(item["order_id"])
            if goods is None and china is None and border is None and hanoi is None:
                if current is not None:
                    db.delete(current)
                continue
            if current is None:
                current = AdSpendOrderCost(order_id=item["order_id"])
                db.add(current)
            current.goods_cny = goods
            current.ship_china_domestic_cny = china
            current.ship_border_to_hanoi_cny = border
            current.ship_hanoi_to_customer_vnd = hanoi
    db.commit()
