import re
from pathlib import Path

import pytest

from scripts.reconcile_order_schema_parity import (
    canonical_payment_ids,
    expected_warehouse_reserved,
    parse_args,
    run_reconcile_mode,
)


def test_reconcile_defaults_to_dry_run():
    assert parse_args([]).apply is False


def test_reconcile_requires_explicit_apply():
    assert parse_args(["--apply"]).apply is True
    with pytest.raises(SystemExit):
        parse_args(["--yes"])


def test_default_mode_is_operationally_read_only():
    calls = []
    result = run_reconcile_mode(
        apply=False,
        audit_fn=lambda: {"duplicate_rows": 3},
        apply_fn=lambda: calls.append("apply"),
    )
    assert calls == []
    assert result == {
        "mode": "dry-run",
        "before": {"duplicate_rows": 3},
    }


def test_payment_canonical_selection_is_deterministic():
    rows = [
        {"id": 3, "payment_status": "pending", "created_at": "2026-01-01"},
        {"id": 2, "payment_status": "deposit_paid", "created_at": "2026-01-02"},
        {"id": 1, "payment_status": "deposit_paid", "created_at": "2026-01-02"},
    ]
    assert canonical_payment_ids(rows) == [1, 2, 3]
    assert canonical_payment_ids(list(reversed(rows))) == [1, 2, 3]


def test_warehouse_reconcile_plan_is_deterministic():
    rows = [
        {"product_id": 9, "quantity": 0},
        {"product_id": 4, "quantity": 2},
        {"product_id": 4, "quantity": 3},
    ]
    assert expected_warehouse_reserved(rows) == [(4, 5), (9, 0)]
    assert expected_warehouse_reserved(list(reversed(rows))) == [(4, 5), (9, 0)]


def test_staged_migrations_are_schema_only():
    migration_dir = Path(__file__).resolve().parents[1] / "database_migrations"
    for name in ("004_parity_hardening.sql", "005_schema_audit_parity.sql"):
        sql = (migration_dir / name).read_text(encoding="utf-8")
        assert re.search(r"^\s*(update|delete|insert)\b", sql, re.I | re.M) is None
        assert re.search(r"create\s+unique\s+index", sql, re.I) is None
