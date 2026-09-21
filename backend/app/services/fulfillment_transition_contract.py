"""Versioned order/fulfillment transition contract shared by APIs and workers."""

from __future__ import annotations

from app.models.order import OrderStatus
from app.services.optimized_fulfillment_feature import (
    select_optimized_fulfillment_outcome,
)

FULFILLMENT_TRANSITION_CONTRACT_VERSION = "2026-09-21.v1"

VALID_ORDER_TRANSITIONS = {
    OrderStatus.PENDING.value: {
        OrderStatus.WAITING_DEPOSIT.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.WAITING_DEPOSIT.value: {
        OrderStatus.DEPOSIT_PAID.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.DEPOSIT_PAID.value: {
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPING.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.CONFIRMED.value: {
        OrderStatus.PROCESSING.value,
        OrderStatus.SHIPPING.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.PROCESSING.value: {
        OrderStatus.SHIPPING.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.SHIPPING.value: {
        OrderStatus.DELIVERED.value,
        OrderStatus.RETURNED.value,
    },
    OrderStatus.DELIVERED.value: {
        OrderStatus.COMPLETED.value,
        OrderStatus.RETURNED.value,
    },
    OrderStatus.COMPLETED.value: {OrderStatus.RETURNED.value},
    OrderStatus.RETURNED.value: set(),
    OrderStatus.CANCELLED.value: set(),
}

SOURCE_ROUTINE_TRANSITIONS = {
    "vietnam": {
        OrderStatus.CONFIRMED.value: {OrderStatus.PROCESSING.value},
        OrderStatus.PROCESSING.value: {OrderStatus.SHIPPING.value},
    },
    "china": {
        OrderStatus.DEPOSIT_PAID.value: {OrderStatus.PROCESSING.value},
        OrderStatus.CONFIRMED.value: {OrderStatus.PROCESSING.value},
        OrderStatus.PROCESSING.value: {OrderStatus.SHIPPING.value},
    },
}


def transition_is_allowed(from_status: str, to_status: str) -> bool:
    return to_status in VALID_ORDER_TRANSITIONS.get(from_status, set())


def transition_is_allowed_for_tenant(
    tenant_id: str,
    from_status: str,
    to_status: str,
) -> bool:
    """Pure lifecycle decision selected before any order mutation is attempted."""
    allowed, _decision = select_optimized_fulfillment_outcome(
        tenant_id=tenant_id,
        operation="shipping",
        legacy=lambda: transition_is_allowed(from_status, to_status),
        optimized=lambda: transition_is_allowed(from_status, to_status),
    )
    return allowed
