#!/usr/bin/env python3
"""Golden contract and sanitized shadow-snapshot parity gate."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REQUIRED_SCENARIOS = (
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
)
VOLATILE_KEYS = {
    "id",
    "order_id",
    "order_code",
    "checkout_group_id",
    "event_id",
    "request_id",
    "trace_id",
    "created_at",
    "updated_at",
    "delivered_at",
    "returned_at",
    "processed_at",
    "duration_ms",
}
TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ][0-9:.+-]+(?:Z|[+-]\d{2}:\d{2})?$"
)


class GateError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot load JSON {path}: {exc}") from exc


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def sanitize_snapshot(value: Any, key: str = "") -> Any:
    if key in VOLATILE_KEYS:
        return f"<{key}>"
    if isinstance(value, dict):
        return {
            candidate: sanitize_snapshot(value[candidate], candidate)
            for candidate in sorted(value)
            if candidate not in {"debug", "stack", "sql", "timing"}
        }
    if isinstance(value, list):
        sanitized = [sanitize_snapshot(item, key) for item in value]
        if all(isinstance(item, dict) and "scenario_id" in item for item in sanitized):
            return sorted(sanitized, key=lambda item: str(item["scenario_id"]))
        return sanitized
    if isinstance(value, str) and TIMESTAMP_RE.fullmatch(value):
        return "<timestamp>"
    return value


def fixture_map(fixture: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = fixture.get("scenarios")
    if not isinstance(rows, list):
        raise GateError("fixture scenarios must be an array")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise GateError("every scenario must have a string id")
        if row["id"] in mapped:
            raise GateError(f"duplicate scenario id: {row['id']}")
        if not isinstance(row.get("input"), dict) or not isinstance(
            row.get("expected"), dict
        ):
            raise GateError(f"scenario {row['id']} needs input and expected objects")
        mapped[row["id"]] = row
    return mapped


def validate_fixture(fixture: dict[str, Any]) -> None:
    if fixture.get("contract_id") != "shared-order-fulfillment":
        raise GateError("unexpected contract_id")
    if fixture.get("fixture_schema_version") != 1:
        raise GateError("unsupported fixture_schema_version")
    if not re.fullmatch(r"1\.\d+\.\d+", str(fixture.get("contract_version", ""))):
        raise GateError("contract_version must be compatible with v1")
    scenarios = fixture_map(fixture)
    missing = [scenario for scenario in REQUIRED_SCENARIOS if scenario not in scenarios]
    if missing:
        raise GateError(f"missing required scenarios: {', '.join(missing)}")

    expected = {key: row["expected"] for key, row in scenarios.items()}
    split_groups = expected["checkout_vn_cn_split"]["groups"]
    if [group["source"] for group in split_groups] != ["vietnam", "china"]:
        raise GateError("mixed checkout order must be stable: vietnam then china")
    if sum(group["shipping_fee"] for group in split_groups) != 30000:
        raise GateError("mixed checkout must charge shipping exactly once")
    if expected["concurrent_sku_reservation"]["successful_reservations"] != 1:
        raise GateError("concurrent SKU fixture must admit exactly one reservation")
    if expected["mixed_checkout_rollback"]["persisted_orders"] != 0:
        raise GateError("mixed checkout failure must roll back every order")
    if expected["cod_stock_reserve"]["reserve_before_confirmation"] is not True:
        raise GateError("COD warehouse stock must reserve during checkout")
    if expected["late_deposit_after_release"]["accepted"] is not False:
        raise GateError("late deposit after released stock must not silently confirm")
    if expected["ems_at_customs_stop"]["cron_advances"] is not False:
        raise GateError("China timeline must stop at customs")
    for replay_id in ("sepay_replay", "ems_event_replay"):
        if expected[replay_id]["replay_is_noop"] is not True:
            raise GateError(f"{replay_id} must be idempotent")
    if expected["cancel_before_deduct_stock"]["stock_restore_count"] != 0:
        raise GateError("cancellation before deduction must not restore physical stock")
    if expected["return_before_deduct_stock"]["stock_restore_count"] != 0:
        raise GateError("return before deduction must only release the reservation")
    if expected["return_after_delivered_stock"]["stock_restore_count"] != 1:
        raise GateError("return after delivered deduction must restore physical stock once")
    if expected["ems_delivered_side_effects"]["replay_is_noop"] is not True:
        raise GateError("delivered side effects must run once")
    affiliate = expected["affiliate_lifecycle"]
    if (
        affiliate["grant_on_deposit"] != 1
        or affiliate["confirm_on_delivered"] != 1
        or affiliate["cancel_on_return"] != 1
        or affiliate["wallet_refund_on_return"] != 0
    ):
        raise GateError("affiliate lifecycle invariant mismatch")


def compare_snapshots(left: Any, right: Any) -> tuple[Any, Any]:
    sanitized_left = sanitize_snapshot(left)
    sanitized_right = sanitize_snapshot(right)
    if canonical_json(sanitized_left) != canonical_json(sanitized_right):
        raise GateError(
            "sanitized shadow snapshots differ\n"
            f"--- baseline\n{canonical_json(sanitized_left)}"
            f"--- candidate\n{canonical_json(sanitized_right)}"
        )
    return sanitized_left, sanitized_right


def validate_shadow_coverage(snapshot: Any, label: str) -> None:
    rows = snapshot.get("scenarios") if isinstance(snapshot, dict) else snapshot
    if not isinstance(rows, list):
        raise GateError(f"{label} snapshot must contain a scenarios array")
    seen = {
        str(row.get("scenario_id"))
        for row in rows
        if isinstance(row, dict) and row.get("scenario_id")
    }
    missing = [scenario for scenario in REQUIRED_SCENARIOS if scenario not in seen]
    if missing:
        raise GateError(
            f"{label} snapshot is missing scenarios: {', '.join(missing)}"
        )


def run_snapshot_command(command: str, tenant_id: str) -> Any:
    env = dict(os.environ)
    env["ORDER_FULFILLMENT_PARITY_TENANT_ID"] = tenant_id
    completed = subprocess.run(
        command,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode:
        raise GateError(
            f"snapshot command failed ({completed.returncode}): {command}\n"
            f"{completed.stderr.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise GateError(f"snapshot command did not emit JSON: {command}") from exc


def run_self_test() -> None:
    baseline = {
        "scenario_id": "replay",
        "order_id": "order-a",
        "created_at": "2026-09-21T10:00:00Z",
        "stock": 3,
        "debug": {"sql": "not contractual"},
    }
    candidate = {
        "stock": 3,
        "created_at": "2026-09-21T11:00:00Z",
        "order_id": "order-b",
        "scenario_id": "replay",
    }
    compare_snapshots(baseline, candidate)
    try:
        compare_snapshots(baseline, {**candidate, "stock": 2})
    except GateError:
        pass
    else:
        raise GateError("self-test failed to detect a contractual snapshot mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "contracts"
        / "shared-order-fulfillment-v1.json",
    )
    parser.add_argument("--peer-fixture", type=Path)
    parser.add_argument("--peer-tool", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--integration", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--tenant-id", default=os.getenv("ORDER_FULFILLMENT_PARITY_TENANT_ID", ""))
    parser.add_argument("--write-sanitized", type=Path)
    args = parser.parse_args()

    try:
        fixture = load_json(args.fixture)
        validate_fixture(fixture)
        if args.self_test:
            run_self_test()
        if args.peer_fixture:
            peer = load_json(args.peer_fixture)
            validate_fixture(peer)
            if args.fixture.read_bytes() != args.peer_fixture.read_bytes():
                raise GateError("contract fixtures are not byte-for-byte identical")
        if args.peer_tool and Path(__file__).read_bytes() != args.peer_tool.read_bytes():
            raise GateError("parity gate tools are not byte-for-byte identical")

        baseline = load_json(args.baseline) if args.baseline else None
        candidate = load_json(args.candidate) if args.candidate else None
        if bool(baseline is not None) != bool(candidate is not None):
            raise GateError("--baseline and --candidate must be supplied together")

        if args.integration:
            required = os.getenv("FULFILLMENT_PARITY_REQUIRE_INTEGRATION") == "1"
            baseline_command = os.getenv("FULFILLMENT_PARITY_BASELINE_CMD", "").strip()
            candidate_command = os.getenv("FULFILLMENT_PARITY_CANDIDATE_CMD", "").strip()
            if not args.tenant_id:
                raise GateError("--tenant-id is required for integration parity")
            if not baseline_command or not candidate_command:
                if required:
                    raise GateError(
                        "integration parity is required but snapshot commands are missing"
                    )
                print("integration parity skipped: snapshot commands are not configured")
            else:
                baseline = run_snapshot_command(baseline_command, args.tenant_id)
                candidate = run_snapshot_command(candidate_command, args.tenant_id)
                validate_shadow_coverage(baseline, "baseline")
                validate_shadow_coverage(candidate, "candidate")

        if baseline is not None and candidate is not None:
            sanitized_left, sanitized_right = compare_snapshots(baseline, candidate)
            if args.write_sanitized:
                args.write_sanitized.mkdir(parents=True, exist_ok=True)
                (args.write_sanitized / "baseline.sanitized.json").write_text(
                    canonical_json(sanitized_left), encoding="utf-8"
                )
                (args.write_sanitized / "candidate.sanitized.json").write_text(
                    canonical_json(sanitized_right), encoding="utf-8"
                )
        print(
            f"fulfillment parity gate passed: "
            f"{fixture['contract_version']} ({len(fixture['scenarios'])} scenarios)"
        )
        return 0
    except GateError as exc:
        print(f"fulfillment parity gate failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
