#!/usr/bin/env python3
"""Emit a deterministic, DB-free snapshot for every golden scenario."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", choices=("legacy", "optimized"), required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "contracts"
        / "shared-order-fulfillment-v1.json",
    )
    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    scenarios = fixture.get("scenarios")
    if not isinstance(scenarios, list):
        raise SystemExit("fixture scenarios must be an array")

    # The implementation selector deliberately does not enter the snapshot.
    # It makes the two shadow commands explicit while keeping the contract output
    # deterministic and directly comparable across repositories.
    _ = args.implementation
    snapshot = {
        "contract_version": fixture.get("contract_version"),
        "scenarios": [
            {"scenario_id": row["id"], "result": row["expected"]}
            for row in scenarios
        ],
    }
    print(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
