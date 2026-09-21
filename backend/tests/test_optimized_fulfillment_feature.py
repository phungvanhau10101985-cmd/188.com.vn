from decimal import Decimal

from app.services import checkout_fulfillment
from app.services import fulfillment_transition_contract
from app.services import order_shipment_timeline
from app.services.optimized_fulfillment_feature import (
    optimized_fulfillment_decision,
    parse_optimized_fulfillment_tenant_modes,
    select_optimized_fulfillment_outcome,
)


def test_feature_is_off_by_default_and_malformed_config_fails_safe():
    assert optimized_fulfillment_decision("tenant-a", {}).effective_mode == "off"
    assert parse_optimized_fulfillment_tenant_modes("{bad json") == {}


def test_shadow_mode_is_tenant_scoped():
    env = {
        "ORDER_FULFILLMENT_OPTIMIZED_TENANTS": (
            '{"tenant-a":"shadow","tenant-b":"off"}'
        )
    }
    assert optimized_fulfillment_decision("tenant-a", env).effective_mode == "shadow"
    assert optimized_fulfillment_decision("tenant-b", env).effective_mode == "off"


def test_enforce_requires_successful_parity_gate():
    blocked = optimized_fulfillment_decision(
        "tenant-a",
        {"ORDER_FULFILLMENT_OPTIMIZED_TENANTS": '{"tenant-a":"enforce"}'},
    )
    assert blocked.effective_mode == "off"
    assert blocked.reason == "enforce_gate_missing"

    enabled = optimized_fulfillment_decision(
        "tenant-a",
        {
            "ORDER_FULFILLMENT_OPTIMIZED_TENANTS": '{"tenant-a":"enforce"}',
            "ORDER_FULFILLMENT_PARITY_GATE_PASSED": "1",
        },
    )
    assert enabled.effective_mode == "enforce"
    assert enabled.reason == "enforce_enabled"


def test_shadow_returns_legacy_and_logs_only_hashes():
    entries: list[dict[str, str]] = []
    value, decision = select_optimized_fulfillment_outcome(
        tenant_id="private-tenant-id",
        operation="payment",
        env={"ORDER_FULFILLMENT_OPTIMIZED_MODE": "shadow"},
        legacy=lambda: {"allowed": True, "secret": "legacy-secret"},
        optimized=lambda: {"allowed": False, "secret": "optimized-secret"},
        log=entries.append,
    )

    assert value == {"allowed": True, "secret": "legacy-secret"}
    assert decision.effective_mode == "shadow"
    assert len(entries) == 1
    serialized = str(entries[0])
    assert "optimized_fulfillment_shadow_mismatch" in serialized
    assert "private-tenant-id" not in serialized
    assert "legacy-secret" not in serialized
    assert "optimized-secret" not in serialized


def test_enforce_selector_stays_legacy_until_gate_passes():
    blocked, blocked_decision = select_optimized_fulfillment_outcome(
        tenant_id="tenant-a",
        operation="shipping",
        env={"ORDER_FULFILLMENT_OPTIMIZED_MODE": "enforce"},
        legacy=lambda: "legacy",
        optimized=lambda: "optimized",
    )
    assert blocked == "legacy"
    assert blocked_decision.reason == "enforce_gate_missing"

    enabled, enabled_decision = select_optimized_fulfillment_outcome(
        tenant_id="tenant-a",
        operation="shipping",
        env={
            "ORDER_FULFILLMENT_OPTIMIZED_MODE": "enforce",
            "ORDER_FULFILLMENT_PARITY_GATE_PASSED": "1",
        },
        legacy=lambda: "legacy",
        optimized=lambda: "optimized",
    )
    assert enabled == "optimized"
    assert enabled_decision.reason == "enforce_enabled"


def test_checkout_runtime_uses_selector_before_mutation(monkeypatch):
    calls: list[tuple[str, str]] = []

    def select(**kwargs):
        calls.append((kwargs["tenant_id"], kwargs["operation"]))
        return kwargs["legacy"](), object()

    monkeypatch.setattr(
        checkout_fulfillment,
        "select_optimized_fulfillment_outcome",
        select,
    )
    grouped = checkout_fulfillment.group_checkout_items_for_tenant(
        "tenant-checkout",
        [
            {"fulfillment_source": "china", "total_price": Decimal("2")},
            {"fulfillment_source": "vietnam", "total_price": Decimal("1")},
        ],
    )

    assert calls == [("tenant-checkout", "checkout")]
    assert list(grouped) == ["vietnam", "china"]


def test_shipment_runtime_uses_selector_for_pure_step_plan(monkeypatch):
    calls: list[tuple[str, str]] = []

    def select(**kwargs):
        calls.append((kwargs["tenant_id"], kwargs["operation"]))
        return kwargs["legacy"](), object()

    monkeypatch.setattr(
        order_shipment_timeline,
        "select_optimized_fulfillment_outcome",
        select,
    )
    steps = order_shipment_timeline._step_defs_for_tenant(
        "tenant-shipment",
        False,
        "vietnam",
    )

    assert calls == [("tenant-shipment", "shipping")]
    assert [step["key"] for step in steps] == [
        "order_confirmed",
        "vn_picking",
        "vn_packed",
        "awaiting_confirm",
    ]


def test_lifecycle_runtime_uses_selector_for_transition_decision(monkeypatch):
    calls: list[tuple[str, str]] = []

    def select(**kwargs):
        calls.append((kwargs["tenant_id"], kwargs["operation"]))
        return kwargs["legacy"](), object()

    monkeypatch.setattr(
        fulfillment_transition_contract,
        "select_optimized_fulfillment_outcome",
        select,
    )

    assert fulfillment_transition_contract.transition_is_allowed_for_tenant(
        "tenant-lifecycle",
        "shipping",
        "delivered",
    )
    assert calls == [("tenant-lifecycle", "shipping")]
