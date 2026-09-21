"""Single transactional hook for every transition into delivered."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus


def mark_order_delivered(
    db: Session,
    order: Order,
    *,
    source: str,
    admin_id: Optional[int] = None,
    previous_status: Optional[str] = None,
) -> bool:
    """Apply delivered state and side effects once. Caller owns commit and notifications."""
    old_status = previous_status or getattr(order.status, "value", order.status)
    if old_status in (OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value):
        return False

    now = datetime.now(timezone.utc)
    order.status = OrderStatus.DELIVERED
    order.delivered_at = order.delivered_at or now
    order.updated_at = now

    from app.services.warehouse_stock import sync_warehouse_stock_on_status_change
    from app.services import affiliate_wallet as affiliate_svc
    from app.services import order_shipment_timeline as shipment_svc

    sync_warehouse_stock_on_status_change(
        db, order, old_status, OrderStatus.DELIVERED.value
    )
    commission_confirmed = affiliate_svc.handle_order_status_change(
        db, order, old_status, OrderStatus.DELIVERED.value
    )
    shipment_svc.mark_delivered_on_timeline(db, order, admin_id=admin_id)

    if order.user_id:
        try:
            from app.services import promotion_grants as grant_svc

            grant_svc.process_first_delivered_grants(db, order.user_id)
        except Exception:
            # Promotions are secondary and retain existing fail-open behavior.
            pass

    if commission_confirmed:
        setattr(order, "_delivery_commission_confirmed", True)
    setattr(order, "_delivery_source", source)
    return True
