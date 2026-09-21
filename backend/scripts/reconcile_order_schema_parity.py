#!/usr/bin/env python3
"""Audit/reconcile fulfillment schema parity. Read-only unless --apply is set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Sequence

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deterministic reconciliation (default: report only).",
    )
    return parser.parse_args(argv)

def canonical_payment_ids(rows: Sequence[dict]) -> list[int]:
    paid = {"deposit_paid", "partially_paid", "paid"}
    return [
        int(row["id"])
        for row in sorted(
            rows,
            key=lambda row: (
                0 if str(row.get("payment_status") or "") in paid else 1,
                str(row.get("confirmed_at") or "9999"),
                str(row.get("created_at") or "9999"),
                int(row["id"]),
            ),
        )
    ]


def expected_warehouse_reserved(rows: Sequence[dict]) -> list[tuple[int, int]]:
    totals: dict[int, int] = {}
    for row in rows:
        product_id = int(row["product_id"])
        totals[product_id] = totals.get(product_id, 0) + max(
            0, int(row.get("quantity") or 0)
        )
    return sorted(totals.items())


def run_reconcile_mode(
    *,
    apply: bool,
    audit_fn: Callable[[], dict],
    apply_fn: Callable[[], None],
) -> dict:
    before = audit_fn()
    if not apply:
        return {"mode": "dry-run", "before": before}
    apply_fn()
    return {"mode": "apply", "before": before, "after": audit_fn()}


def _count(conn, sql: str) -> int:
    from sqlalchemy import text

    return int(conn.execute(text(sql)).scalar() or 0)


def _schema(inspector) -> dict[str, set[str]]:
    tables = set(inspector.get_table_names())
    return {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in (
            "products", "orders", "order_items", "order_shipment_events",
            "payments", "product_reviews", "product_review_useful_votes",
            "notifications", "parity_reconcile_archive",
        )
        if table in tables
    }


def audit(conn, columns: dict[str, set[str]]) -> dict:
    timeline_ready = "timeline_schema_version" in columns.get("orders", set())
    shipment_columns = columns.get("order_shipment_events", set())
    shipment_ready = {"actor_type", "actor_id", "idempotency_key"} <= shipment_columns
    warehouse_ready = (
        "warehouse_reserved" in columns.get("products", set())
        and "warehouse_stock_additive" in columns.get("order_items", set())
    )
    archive_ready = "parity_reconcile_archive" in columns
    return {
        "warehouse_reserved": {
            "schema_missing": not warehouse_ready,
            "negative_products": None if not warehouse_ready else _count(
                conn, "SELECT COUNT(*) FROM products WHERE warehouse_reserved < 0"
            ),
            "legacy_hold_lines": None if not warehouse_ready else _count(conn, """
                SELECT COUNT(*) FROM order_items
                WHERE product_id IS NOT NULL
                  AND warehouse_stock_reserved_at IS NOT NULL
                  AND warehouse_stock_deducted_at IS NULL
                  AND warehouse_stock_additive IS FALSE
            """),
            "legacy_hold_quantity": None if not warehouse_ready else _count(conn, """
                SELECT COALESCE(SUM(CASE WHEN COALESCE(quantity, 0) > 0
                  THEN quantity ELSE 0 END), 0)
                FROM order_items
                WHERE product_id IS NOT NULL
                  AND warehouse_stock_reserved_at IS NOT NULL
                  AND warehouse_stock_deducted_at IS NULL
                  AND warehouse_stock_additive IS FALSE
            """),
            "mismatched_products": None if not warehouse_ready else _count(conn, """
                WITH expected AS (
                  SELECT oi.product_id, SUM(CASE WHEN COALESCE(oi.quantity, 0) > 0 THEN oi.quantity ELSE 0 END) quantity
                  FROM order_items oi
                  WHERE oi.warehouse_stock_reserved_at IS NOT NULL
                    AND oi.warehouse_stock_deducted_at IS NULL
                  GROUP BY oi.product_id
                )
                SELECT COUNT(*) FROM products p
                LEFT JOIN expected e ON e.product_id = p.id
                WHERE COALESCE(p.warehouse_reserved, 0) <> COALESCE(e.quantity, 0)
            """),
        },
        "timeline_schema_version": {
            "schema_missing": not timeline_ready,
            "orders_not_v1": None if not timeline_ready else _count(
                conn, "SELECT COUNT(*) FROM orders WHERE COALESCE(timeline_schema_version, 0) <> 1"
            ),
        },
        "shipment_event_actor_idempotency": {
            "schema_missing": not shipment_ready,
            "missing_actor_type": None if not shipment_ready else _count(conn, """
                SELECT COUNT(*) FROM order_shipment_events
                WHERE actor_type IS NULL OR TRIM(actor_type) = ''
            """),
            "actor_rows_to_reconcile": None if not shipment_ready else _count(conn, """
                SELECT COUNT(*) FROM order_shipment_events
                WHERE updated_by_admin_id IS NOT NULL
                  AND (actor_type <> 'admin'
                       OR actor_id IS DISTINCT FROM CAST(updated_by_admin_id AS VARCHAR))
            """),
            "missing_idempotency_key": None if not shipment_ready else _count(conn, """
                SELECT COUNT(*) FROM order_shipment_events
                WHERE idempotency_key IS NULL OR TRIM(idempotency_key) = ''
            """),
            "duplicate_keys": None if not shipment_ready else _count(conn, """
                SELECT COUNT(*) FROM (
                  SELECT order_id, idempotency_key FROM order_shipment_events
                  WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) <> ''
                  GROUP BY order_id, idempotency_key HAVING COUNT(*) > 1
                ) d
            """),
            "duplicate_rows": None if not shipment_ready else _count(conn, """
                SELECT COALESCE(SUM(n - 1), 0) FROM (
                  SELECT COUNT(*) n FROM order_shipment_events
                  WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) <> ''
                  GROUP BY order_id, idempotency_key HAVING COUNT(*) > 1
                ) d
            """),
        },
        "sepay_payment_duplicates": {
            "schema_missing": not archive_ready,
            "duplicate_keys": _count(conn, """
                SELECT COUNT(*) FROM (
                  SELECT transaction_code FROM payments
                  WHERE payment_type LIKE 'deposit_sepay%'
                    AND transaction_code IS NOT NULL AND TRIM(transaction_code) <> ''
                  GROUP BY transaction_code HAVING COUNT(*) > 1
                ) d
            """),
            "duplicate_rows": _count(conn, """
                SELECT COALESCE(SUM(n - 1), 0) FROM (
                  SELECT COUNT(*) n FROM payments
                  WHERE payment_type LIKE 'deposit_sepay%'
                    AND transaction_code IS NOT NULL AND TRIM(transaction_code) <> ''
                  GROUP BY transaction_code HAVING COUNT(*) > 1
                ) d
            """),
        },
        "customer_review_duplicates": {
            "schema_missing": not archive_ready,
            "duplicate_keys": _count(conn, """
                SELECT COUNT(*) FROM (
                  SELECT user_id, product_id FROM product_reviews
                  WHERE user_id IS NOT NULL AND product_id IS NOT NULL
                  GROUP BY user_id, product_id HAVING COUNT(*) > 1
                ) d
            """),
            "duplicate_rows": _count(conn, """
                SELECT COALESCE(SUM(n - 1), 0) FROM (
                  SELECT COUNT(*) n FROM product_reviews
                  WHERE user_id IS NOT NULL AND product_id IS NOT NULL
                  GROUP BY user_id, product_id HAVING COUNT(*) > 1
                ) d
            """),
        },
        "notification_duplicates": {
            "schema_missing": not archive_ready,
            "duplicate_keys": _count(conn, """
                SELECT COUNT(*) FROM (
                  SELECT dedupe_key FROM notifications
                  WHERE dedupe_key IS NOT NULL AND TRIM(dedupe_key) <> ''
                  GROUP BY dedupe_key HAVING COUNT(*) > 1
                ) d
            """),
            "duplicate_rows": _count(conn, """
                SELECT COALESCE(SUM(n - 1), 0) FROM (
                  SELECT COUNT(*) n FROM notifications
                  WHERE dedupe_key IS NOT NULL AND TRIM(dedupe_key) <> ''
                  GROUP BY dedupe_key HAVING COUNT(*) > 1
                ) d
            """),
        },
    }


def reconcile(conn, columns: dict[str, set[str]]) -> None:
    from sqlalchemy import text

    required = {
        "orders": {"timeline_schema_version"},
        "order_shipment_events": {"actor_type", "actor_id", "idempotency_key"},
        "products": {"warehouse_reserved"},
        "order_items": {"warehouse_stock_additive"},
        "parity_reconcile_archive": {"entity_type", "original_id", "payload"},
        "payments": {"transaction_code", "payment_type", "payment_status"},
        "product_reviews": {"user_id", "product_id"},
        "product_review_useful_votes": {"review_id"},
        "notifications": {"dedupe_key"},
    }
    missing = {
        table: sorted(names - columns.get(table, set()))
        for table, names in required.items()
        if names - columns.get(table, set())
    }
    if missing:
        raise RuntimeError(
            "Apply backend/database_migrations/004_parity_hardening.sql and "
            "backend/database_migrations/005_schema_audit_parity.sql first; "
            f"missing columns: {missing}"
        )

    conn.execute(text("""
        WITH legacy_holds AS (
          SELECT product_id,
                 SUM(CASE WHEN COALESCE(quantity, 0) > 0 THEN quantity ELSE 0 END) quantity
          FROM order_items
          WHERE product_id IS NOT NULL
            AND warehouse_stock_reserved_at IS NOT NULL
            AND warehouse_stock_deducted_at IS NULL
            AND warehouse_stock_additive IS FALSE
          GROUP BY product_id
        )
        UPDATE products p
        SET available = COALESCE(p.available, 0) + h.quantity
        FROM legacy_holds h WHERE p.id = h.product_id
    """))
    conn.execute(text("""
        UPDATE order_items oi
        SET warehouse_stock_additive = TRUE
        WHERE oi.product_id IS NOT NULL
          AND EXISTS (SELECT 1 FROM products p WHERE p.id = oi.product_id)
          AND oi.warehouse_stock_reserved_at IS NOT NULL
          AND oi.warehouse_stock_deducted_at IS NULL
          AND oi.warehouse_stock_additive IS FALSE
    """))
    conn.execute(text("""
        WITH expected AS (
          SELECT oi.product_id, SUM(CASE WHEN COALESCE(oi.quantity, 0) > 0 THEN oi.quantity ELSE 0 END) quantity
          FROM order_items oi
          WHERE oi.warehouse_stock_reserved_at IS NOT NULL
            AND oi.warehouse_stock_deducted_at IS NULL
          GROUP BY oi.product_id
        )
        UPDATE products
        SET warehouse_reserved = COALESCE((
          SELECT expected.quantity FROM expected WHERE expected.product_id = products.id
        ), 0)
        WHERE COALESCE(warehouse_reserved, 0) <> COALESCE((
          SELECT expected.quantity FROM expected WHERE expected.product_id = products.id
        ), 0)
    """))
    conn.execute(text(
        "UPDATE orders SET timeline_schema_version = 1 "
        "WHERE COALESCE(timeline_schema_version, 0) <> 1"
    ))
    conn.execute(text("""
        UPDATE order_shipment_events
        SET actor_type = CASE WHEN updated_by_admin_id IS NOT NULL THEN 'admin' ELSE 'system' END,
            actor_id = CASE WHEN updated_by_admin_id IS NOT NULL THEN CAST(updated_by_admin_id AS VARCHAR) ELSE actor_id END,
            idempotency_key = COALESCE(
              NULLIF(TRIM(idempotency_key), ''),
              'legacy:event:' || CAST(id AS VARCHAR)
            )
        WHERE actor_type IS NULL OR TRIM(actor_type) = ''
           OR (updated_by_admin_id IS NOT NULL
               AND (actor_type <> 'admin'
                    OR actor_id IS DISTINCT FROM CAST(updated_by_admin_id AS VARCHAR)))
           OR idempotency_key IS NULL OR TRIM(idempotency_key) = ''
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT p.*,
            FIRST_VALUE(id) OVER (
              PARTITION BY transaction_code
              ORDER BY CASE WHEN payment_status::text IN
                ('deposit_paid', 'partially_paid', 'paid') THEN 0 ELSE 1 END,
                confirmed_at NULLS LAST, created_at NULLS LAST, id
            ) canonical_id,
            ROW_NUMBER() OVER (
              PARTITION BY transaction_code
              ORDER BY CASE WHEN payment_status::text IN
                ('deposit_paid', 'partially_paid', 'paid') THEN 0 ELSE 1 END,
                confirmed_at NULLS LAST, created_at NULLS LAST, id
            ) rn
          FROM payments p
          WHERE payment_type LIKE 'deposit_sepay%'
            AND transaction_code IS NOT NULL AND TRIM(transaction_code) <> ''
        )
        INSERT INTO parity_reconcile_archive (
          entity_type, original_id, canonical_id, dedupe_key, payload
        )
        SELECT 'sepay_payment', id::text, canonical_id::text, transaction_code,
               to_jsonb(ranked) - 'canonical_id' - 'rn'
        FROM ranked WHERE rn > 1
        ON CONFLICT (entity_type, original_id) DO NOTHING
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY transaction_code
            ORDER BY CASE WHEN payment_status::text IN
              ('deposit_paid', 'partially_paid', 'paid') THEN 0 ELSE 1 END,
              confirmed_at NULLS LAST, created_at NULLS LAST, id
          ) rn
          FROM payments
          WHERE payment_type LIKE 'deposit_sepay%'
            AND transaction_code IS NOT NULL AND TRIM(transaction_code) <> ''
        )
        UPDATE payments p SET transaction_code = NULL
        FROM ranked r WHERE p.id = r.id AND r.rn > 1
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT r.*,
            FIRST_VALUE(id) OVER (
              PARTITION BY user_id, product_id
              ORDER BY created_at NULLS LAST, id
            ) canonical_id,
            ROW_NUMBER() OVER (
              PARTITION BY user_id, product_id
              ORDER BY created_at NULLS LAST, id
            ) rn
          FROM product_reviews r
          WHERE user_id IS NOT NULL AND product_id IS NOT NULL
        )
        INSERT INTO parity_reconcile_archive (
          entity_type, original_id, canonical_id, dedupe_key, payload
        )
        SELECT 'product_review', r.id::text, r.canonical_id::text,
               r.user_id::text || ':' || r.product_id::text,
               jsonb_build_object(
                 'review', to_jsonb(r) - 'canonical_id' - 'rn',
                 'useful_votes', COALESCE((
                   SELECT jsonb_agg(to_jsonb(v) ORDER BY v.id)
                   FROM product_review_useful_votes v WHERE v.review_id = r.id
                 ), '[]'::jsonb)
               )
        FROM ranked r WHERE r.rn > 1
        ON CONFLICT (entity_type, original_id) DO NOTHING
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY user_id, product_id
            ORDER BY created_at NULLS LAST, id
          ) rn
          FROM product_reviews
          WHERE user_id IS NOT NULL AND product_id IS NOT NULL
        )
        DELETE FROM product_reviews r USING ranked d
        WHERE r.id = d.id AND d.rn > 1
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT n.*,
            FIRST_VALUE(id) OVER (
              PARTITION BY dedupe_key ORDER BY created_at NULLS LAST, id
            ) canonical_id,
            ROW_NUMBER() OVER (
              PARTITION BY dedupe_key ORDER BY created_at NULLS LAST, id
            ) rn
          FROM notifications n
          WHERE dedupe_key IS NOT NULL AND TRIM(dedupe_key) <> ''
        )
        INSERT INTO parity_reconcile_archive (
          entity_type, original_id, canonical_id, dedupe_key, payload
        )
        SELECT 'notification', id::text, canonical_id::text, dedupe_key,
               to_jsonb(ranked) - 'canonical_id' - 'rn'
        FROM ranked WHERE rn > 1
        ON CONFLICT (entity_type, original_id) DO NOTHING
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY dedupe_key ORDER BY created_at NULLS LAST, id
          ) rn
          FROM notifications
          WHERE dedupe_key IS NOT NULL AND TRIM(dedupe_key) <> ''
        )
        DELETE FROM notifications n USING ranked d
        WHERE n.id = d.id AND d.rn > 1
    """))
    conn.execute(text("""
        WITH ranked AS (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY order_id, idempotency_key
            ORDER BY created_at NULLS LAST, id
          ) rn
          FROM order_shipment_events
          WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) <> ''
        )
        UPDATE order_shipment_events e
        SET idempotency_key = 'legacy:event:' || e.id::text
        FROM ranked r WHERE e.id = r.id AND r.rn > 1
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_sepay_transaction_code
        ON payments (transaction_code)
        WHERE payment_type LIKE 'deposit_sepay%'
          AND transaction_code IS NOT NULL AND TRIM(transaction_code) <> ''
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_product_reviews_user_product
        ON product_reviews (user_id, product_id)
        WHERE user_id IS NOT NULL AND product_id IS NOT NULL
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_notifications_dedupe_key
        ON notifications (dedupe_key)
        WHERE dedupe_key IS NOT NULL AND TRIM(dedupe_key) <> ''
    """))
    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_order_shipment_events_idempotency
        ON order_shipment_events (order_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL AND TRIM(idempotency_key) <> ''
    """))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    from sqlalchemy import inspect
    from app.db.session import engine

    columns = _schema(inspect(engine))
    def audit_now() -> dict:
        with engine.connect() as conn:
            return audit(conn, columns)

    def apply_now() -> None:
        with engine.begin() as conn:
            reconcile(conn, columns)

    result = run_reconcile_mode(
        apply=args.apply,
        audit_fn=audit_now,
        apply_fn=apply_now,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
