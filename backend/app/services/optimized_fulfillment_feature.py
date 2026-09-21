"""Tenant-scoped rollout gate for optimized order fulfillment."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from dataclasses import dataclass
from typing import Any, Callable, Mapping

VALID_MODES = {"off", "shadow", "enforce"}


@dataclass(frozen=True)
class OptimizedFulfillmentDecision:
    tenant_id: str
    requested_mode: str
    effective_mode: str
    parity_gate_passed: bool
    reason: str


def _mode_of(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_MODES else None


def parse_optimized_fulfillment_tenant_modes(raw: str | None) -> dict[str, str]:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {
        str(tenant_id).strip(): mode
        for tenant_id, candidate in value.items()
        if str(tenant_id).strip() and (mode := _mode_of(candidate))
    }


def optimized_fulfillment_decision(
    tenant_id: str,
    env: Mapping[str, str] | None = None,
) -> OptimizedFulfillmentDecision:
    values = os.environ if env is None else env
    normalized_tenant_id = tenant_id.strip()
    overrides = parse_optimized_fulfillment_tenant_modes(
        values.get("ORDER_FULFILLMENT_OPTIMIZED_TENANTS")
    )
    requested_mode = (
        overrides.get(normalized_tenant_id)
        or _mode_of(values.get("ORDER_FULFILLMENT_OPTIMIZED_MODE"))
        or "off"
    )
    parity_gate_passed = values.get("ORDER_FULFILLMENT_PARITY_GATE_PASSED") == "1"

    if requested_mode == "enforce" and not parity_gate_passed:
        return OptimizedFulfillmentDecision(
            tenant_id=normalized_tenant_id,
            requested_mode=requested_mode,
            effective_mode="off",
            parity_gate_passed=False,
            reason="enforce_gate_missing",
        )
    return OptimizedFulfillmentDecision(
        tenant_id=normalized_tenant_id,
        requested_mode=requested_mode,
        effective_mode=requested_mode,
        parity_gate_passed=parity_gate_passed,
        reason={
            "off": "disabled",
            "shadow": "shadow_enabled",
            "enforce": "enforce_enabled",
        }[requested_mode],
    )


def _safe_hash(value: object, length: int = 16) -> str:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda item: type(item).__name__,
        )
    except (TypeError, ValueError):
        serialized = type(value).__name__
    return sha256(serialized.encode("utf-8")).hexdigest()[:length]


def select_optimized_fulfillment_outcome(
    *,
    tenant_id: str,
    operation: str,
    legacy: Callable[[], Any],
    optimized: Callable[[], Any],
    env: Mapping[str, str] | None = None,
    log: Callable[[dict[str, str]], None] | None = None,
) -> tuple[Any, OptimizedFulfillmentDecision]:
    """Select a pure result; shadow always returns legacy and logs hashes only."""

    decision = optimized_fulfillment_decision(tenant_id, env)
    if decision.effective_mode == "enforce":
        return optimized(), decision

    legacy_value = legacy()
    if decision.effective_mode != "shadow":
        return legacy_value, decision

    emit = log or (lambda entry: print(json.dumps(entry, sort_keys=True)))
    try:
        optimized_value = optimized()
        if legacy_value != optimized_value:
            emit(
                {
                    "event": "optimized_fulfillment_shadow_mismatch",
                    "operation": operation,
                    "tenantHash": _safe_hash(tenant_id, 12),
                    "legacyHash": _safe_hash(legacy_value),
                    "optimizedHash": _safe_hash(optimized_value),
                }
            )
    except Exception as exc:  # shadow must never replace or break legacy
        emit(
            {
                "event": "optimized_fulfillment_shadow_error",
                "operation": operation,
                "tenantHash": _safe_hash(tenant_id, 12),
                "errorType": type(exc).__name__,
            }
        )
    return legacy_value, decision
