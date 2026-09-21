import json
import re
from pathlib import Path

from app.services.order_shipment_timeline import EMS_IMPORT_DELIVERED_PHASES


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "shared-order-fulfillment-v1.json"
)


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _scenario(fixture: dict, scenario_id: str) -> dict:
    found = next(
        (row for row in fixture["scenarios"] if row["id"] == scenario_id),
        None,
    )
    assert found is not None, f"missing golden scenario: {scenario_id}"
    assert found["topic"]
    assert isinstance(found["input"], dict)
    assert isinstance(found["expected"], dict)
    return found


def test_shared_contract_version_and_scenario_set():
    fixture = _fixture()
    assert fixture["contract_id"] == "shared-order-fulfillment"
    assert re.fullmatch(r"1\.\d+\.\d+", fixture["contract_version"])
    assert fixture["fixture_schema_version"] == 1
    assert fixture["currency"] == "VND"
    assert fixture["timezone"] == "Asia/Ho_Chi_Minh"
    assert [row["id"] for row in fixture["scenarios"]] == [
        "checkout_vn_cn_split",
        "concurrent_sku_reservation",
        "mixed_checkout_rollback",
        "cod_stock_reserve",
        "deposit_sla",
        "late_deposit_after_release",
        "sepay_replay",
        "ems_event_replay",
        "ems_at_customs_stop",
        "ems_delivered_side_effects",
        "cancel_before_deduct_stock",
        "return_before_deduct_stock",
        "return_after_delivered_stock",
        "ems_returned_side_effects",
        "affiliate_lifecycle",
    ]


def test_checkout_and_deposit_sla_golden_invariants():
    fixture = _fixture()
    checkout = _scenario(fixture, "checkout_vn_cn_split")["expected"]
    groups = checkout["groups"]
    assert [row["source"] for row in groups] == ["vietnam", "china"]
    assert sum(row["discount"] for row in groups) == 100000
    assert sum(row["shipping_fee"] for row in groups) == 30000
    assert [row["required_deposit"] for row in groups] == [108000, 162000]
    assert checkout["atomic"] is True
    assert checkout["deposit_base_excludes_shipping"] is True

    deposit = _scenario(fixture, "deposit_sla")["expected"]
    assert deposit["reminder_hours"] == [2, 20]
    assert deposit["vietnam_stock_release_hour"] == 24
    assert deposit["china_stock_release"] is False
    assert deposit["auto_cancel_china"] is False


def test_replay_customs_and_terminal_side_effect_invariants():
    fixture = _fixture()
    replay = _scenario(fixture, "sepay_replay")["expected"]
    assert replay["same_transaction_replay"] == "acknowledged_duplicate"
    for key in (
        "payment_mutations",
        "paid_amount_increments",
        "payment_events",
        "customer_notifications",
        "owner_notifications",
        "affiliate_grants",
    ):
        assert replay[key] == 1, f"{key} must happen once"

    customs = _scenario(fixture, "ems_at_customs_stop")["expected"]
    assert customs["active_step"] == "at_customs"
    assert customs["cron_advances"] is False
    assert customs["customer_can_confirm_received"] is False

    delivered = _scenario(fixture, "ems_delivered_side_effects")["expected"]
    assert delivered["warehouse_stock"] == "deduct_once"
    assert delivered["affiliate_commission"] == "confirm_once"
    assert delivered["replay_is_noop"] is True

    returned = _scenario(fixture, "ems_returned_side_effects")["expected"]
    assert returned["shop_confirmation_required"] is True
    assert returned["warehouse_stock"] == "restore_once"
    assert returned["affiliate_commission"] == "cancel_once"
    assert returned["affiliate_wallet_refund"] is False
    assert returned["replay_is_noop"] is True


def test_cod_settlement_alone_is_not_delivery_evidence():
    assert "delivered" in EMS_IMPORT_DELIVERED_PHASES
    assert "cod_collected" not in EMS_IMPORT_DELIVERED_PHASES
    assert "cod_settled" not in EMS_IMPORT_DELIVERED_PHASES
