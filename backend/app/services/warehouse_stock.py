"""
Tồn kho thanh lý: giữ khi đã cọc/xác nhận, trừ khi giao thành công, hoàn khi hủy/hoàn hàng.

- Chưa cọc (waiting_deposit): `available` và `warehouse_reserved` không đổi; checkout chặn nếu hết chỗ bán.
- Đã cọc / confirmed: `warehouse_reserved` += qty (giữ chỗ, chưa trừ `available`).
- Giao thành công (delivered): `available` -= qty, `warehouse_reserved` -= qty.
- Hủy trước giao / hoàn sau giao: hoàn reserve hoặc cộng lại `available`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session, noload, selectinload

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product
from app.services.warehouse_clearance import is_warehouse_cart_product

logger = logging.getLogger(__name__)

COMMITTED_STATUSES = frozenset(
    {
        OrderStatus.DEPOSIT_PAID.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPING.value,
        OrderStatus.DELIVERED.value,
        OrderStatus.COMPLETED.value,
    }
)


class WarehouseStockError(Exception):
    def __init__(self, message: str, *, product_id: Optional[int] = None):
        self.message = message
        self.product_id = product_id
        super().__init__(message)


def warehouse_sellable_qty(product: Product) -> int:
    """Số lượng có thể bán = tồn thực − đang giữ cho đơn đã cọc."""
    avail = max(0, int(product.available or 0))
    reserved = max(0, int(getattr(product, "warehouse_reserved", 0) or 0))
    return max(0, avail - reserved)


def _lock_product(db: Session, product_id: int) -> Optional[Product]:
    """Khóa hàng Product — không join category (PostgreSQL cấm FOR UPDATE trên OUTER JOIN)."""
    return (
        db.query(Product)
        .options(noload(Product.category_rel))
        .filter(Product.id == product_id)
        .with_for_update(of=Product)
        .first()
    )


def _warehouse_order_items(order: Order) -> List[OrderItem]:
    items = list(order.items or [])
    out: List[OrderItem] = []
    for item in items:
        product = item.product
        if product is None:
            continue
        if is_warehouse_cart_product(product):
            out.append(item)
    return out


def validate_warehouse_checkout_lines(
    db: Session,
    lines: Sequence[Tuple[Product, int]],
) -> None:
    """Chặn đặt hàng khi không đủ chỗ bán (available − reserved)."""
    totals: dict[int, int] = {}
    products_by_id: dict[int, Product] = {}
    for product, qty in lines:
        if qty <= 0 or not is_warehouse_cart_product(product):
            continue
        pid = int(product.id)
        totals[pid] = totals.get(pid, 0) + qty
        products_by_id[pid] = product
    for pid, qty in totals.items():
        locked = _lock_product(db, pid) or products_by_id[pid]
        sellable = warehouse_sellable_qty(locked)
        if sellable < qty:
            name = (locked.name or locked.product_id or "").strip() or f"#{pid}"
            raise WarehouseStockError(
                f"Sản phẩm thanh lý «{name}» chỉ còn {sellable} — không đủ số lượng đặt ({qty}).",
                product_id=pid,
            )


def _order_needs_reserve(order: Order) -> bool:
    st = getattr(order.status, "value", order.status)
    return st in COMMITTED_STATUSES


def reserve_warehouse_stock_for_order(db: Session, order: Order) -> None:
    """Giữ tồn sau khi khách đã cọc hoặc đơn confirmed (không cọc). Idempotent."""
    if not _order_needs_reserve(order):
        return
    items = _warehouse_order_items(order)
    if not items:
        return
    now = datetime.now(timezone.utc)
    for item in items:
        if item.warehouse_stock_reserved_at is not None:
            continue
        qty = max(0, int(item.quantity or 0))
        if qty <= 0:
            continue
        product = _lock_product(db, int(item.product_id))
        if product is None:
            raise WarehouseStockError(
                f"Không tìm thấy sản phẩm kho (id={item.product_id}).",
                product_id=item.product_id,
            )
        sellable = warehouse_sellable_qty(product)
        if sellable < qty:
            name = (product.name or product.product_id or "").strip()
            raise WarehouseStockError(
                f"«{name}» vừa hết chỗ — chỉ còn {sellable}, đơn cần {qty}. Vui lòng hủy đơn hoặc liên hệ shop.",
                product_id=product.id,
            )
        product.warehouse_reserved = max(
            0, int(getattr(product, "warehouse_reserved", 0) or 0) + qty
        )
        item.warehouse_stock_reserved_at = now
    logger.info("warehouse_stock reserve order_id=%s lines=%s", order.id, len(items))


def release_warehouse_stock_for_order(db: Session, order: Order) -> None:
    """Hủy giữ chỗ — đơn chưa giao / chưa trừ tồn thực."""
    items = _warehouse_order_items(order)
    for item in items:
        if item.warehouse_stock_reserved_at is None:
            continue
        if item.warehouse_stock_deducted_at is not None:
            continue
        qty = max(0, int(item.quantity or 0))
        if qty <= 0:
            item.warehouse_stock_reserved_at = None
            continue
        product = _lock_product(db, int(item.product_id))
        if product is not None:
            product.warehouse_reserved = max(
                0, int(getattr(product, "warehouse_reserved", 0) or 0) - qty
            )
        item.warehouse_stock_reserved_at = None
    logger.info("warehouse_stock release order_id=%s", order.id)


def deduct_warehouse_stock_for_order(db: Session, order: Order) -> None:
    """Giao thành công — trừ tồn thực và bỏ giữ chỗ."""
    items = _warehouse_order_items(order)
    now = datetime.now(timezone.utc)
    for item in items:
        if item.warehouse_stock_deducted_at is not None:
            continue
        qty = max(0, int(item.quantity or 0))
        if qty <= 0:
            item.warehouse_stock_deducted_at = now
            continue
        product = _lock_product(db, int(item.product_id))
        if product is None:
            logger.warning(
                "warehouse_stock deduct skip missing product order_id=%s product_id=%s",
                order.id,
                item.product_id,
            )
            continue
        was_reserved = item.warehouse_stock_reserved_at is not None
        reserved = max(0, int(getattr(product, "warehouse_reserved", 0) or 0))
        if was_reserved:
            product.warehouse_reserved = max(0, reserved - qty)
        product.available = max(0, int(product.available or 0) - qty)
        item.warehouse_stock_deducted_at = now
        if was_reserved:
            item.warehouse_stock_reserved_at = None
    logger.info("warehouse_stock deduct order_id=%s", order.id)


def restore_warehouse_stock_for_order(db: Session, order: Order) -> None:
    """Hoàn hàng / giao không thành công — cộng lại tồn nếu đã trừ; ngược lại chỉ bỏ giữ."""
    items = _warehouse_order_items(order)
    for item in items:
        qty = max(0, int(item.quantity or 0))
        if qty <= 0:
            item.warehouse_stock_reserved_at = None
            item.warehouse_stock_deducted_at = None
            continue
        product = _lock_product(db, int(item.product_id))
        if product is None:
            item.warehouse_stock_reserved_at = None
            item.warehouse_stock_deducted_at = None
            continue
        if item.warehouse_stock_deducted_at is not None:
            product.available = max(0, int(product.available or 0) + qty)
            item.warehouse_stock_deducted_at = None
            item.warehouse_stock_reserved_at = None
            logger.info(
                "warehouse_stock restore deducted order_id=%s product_id=%s qty=%s",
                order.id,
                product.id,
                qty,
            )
        elif item.warehouse_stock_reserved_at is not None:
            product.warehouse_reserved = max(
                0, int(getattr(product, "warehouse_reserved", 0) or 0) - qty
            )
            item.warehouse_stock_reserved_at = None
    logger.info("warehouse_stock restore order_id=%s", order.id)


def sync_warehouse_stock_on_status_change(
    db: Session,
    order: Order,
    old_status: Optional[str],
    new_status: str,
) -> None:
    """Gọi sau khi đổi status đơn (admin / khách / hoàn shop)."""
    old = (old_status or "").strip().lower()
    new = (new_status or "").strip().lower()
    if old == new:
        return

    order_loaded = (
        db.query(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .filter(Order.id == order.id)
        .first()
    )
    if order_loaded is None:
        return
    order = order_loaded

    if new == OrderStatus.DELIVERED.value and old != OrderStatus.DELIVERED.value:
        reserve_warehouse_stock_for_order(db, order)
        deduct_warehouse_stock_for_order(db, order)
        return

    if new == OrderStatus.RETURNED.value:
        restore_warehouse_stock_for_order(db, order)
        return

    if new == OrderStatus.CANCELLED.value:
        restore_warehouse_stock_for_order(db, order)
        return

    if new in COMMITTED_STATUSES and old in (
        OrderStatus.WAITING_DEPOSIT.value,
        OrderStatus.PENDING.value,
        "",
    ):
        reserve_warehouse_stock_for_order(db, order)


def reload_order_with_items(db: Session, order_id: int) -> Optional[Order]:
    return (
        db.query(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .filter(Order.id == order_id)
        .first()
    )
