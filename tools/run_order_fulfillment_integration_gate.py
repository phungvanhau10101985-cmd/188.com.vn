#!/usr/bin/env python3
"""Run deterministic cross-repo parity, or an explicitly enabled live gate."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


def shell_command(parts: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--peer-root", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    peer_root = args.peer_root.resolve()
    fixture = root / "contracts" / "shared-order-fulfillment-v1.json"
    peer_fixture = peer_root / "contracts" / "shared-order-fulfillment-v1.json"
    gate = root / "tools" / "order_fulfillment_parity.py"

    env = dict(os.environ)
    tenant_id = env.get("ORDER_FULFILLMENT_PARITY_TENANT_ID", "").strip()
    if args.live:
        if env.get("ORDER_FULFILLMENT_PARITY_LIVE") != "1":
            print(
                "live parity is disabled; set ORDER_FULFILLMENT_PARITY_LIVE=1",
                file=sys.stderr,
            )
            return 2
        env["FULFILLMENT_PARITY_REQUIRE_INTEGRATION"] = "1"
        if not tenant_id:
            print(
                "ORDER_FULFILLMENT_PARITY_TENANT_ID is required for live parity",
                file=sys.stderr,
            )
            return 2
    else:
        tenant_id = "deterministic-fixture"
        env["FULFILLMENT_PARITY_REQUIRE_INTEGRATION"] = "1"
        env["FULFILLMENT_PARITY_BASELINE_CMD"] = shell_command(
            [
                sys.executable,
                str(root / "tools" / "order_fulfillment_fixture_snapshot.py"),
                "--implementation",
                "legacy",
            ]
        )
        env["FULFILLMENT_PARITY_CANDIDATE_CMD"] = shell_command(
            [
                sys.executable,
                str(peer_root / "tools" / "order_fulfillment_fixture_snapshot.py"),
                "--implementation",
                "optimized",
            ]
        )

    completed = subprocess.run(
        [
            sys.executable,
            str(gate),
            "--self-test",
            "--fixture",
            str(fixture),
            "--peer-fixture",
            str(peer_fixture),
            "--peer-tool",
            str(peer_root / "tools" / "order_fulfillment_parity.py"),
            "--integration",
            "--tenant-id",
            tenant_id,
        ],
        check=False,
        env=env,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
