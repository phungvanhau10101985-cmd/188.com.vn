-- Additive parity hardening (PostgreSQL).
-- Historical business rows are intentionally untouched. Run the parity
-- reconciler without flags first, then use explicit --apply.

ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(160);

CREATE TABLE IF NOT EXISTS parity_reconcile_archive (
    id BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(80) NOT NULL,
    original_id VARCHAR(100) NOT NULL,
    canonical_id VARCHAR(100),
    dedupe_key VARCHAR(500) NOT NULL DEFAULT '',
    payload JSONB NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_type, original_id)
);

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS timeline_schema_version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE order_shipment_events
    ADD COLUMN IF NOT EXISTS actor_type VARCHAR(20) NOT NULL DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS actor_id VARCHAR(100),
    ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(160);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'order_shipment_events_actor_type_check'
    ) THEN
        ALTER TABLE order_shipment_events
            ADD CONSTRAINT order_shipment_events_actor_type_check
            CHECK (actor_type IN ('system', 'cron', 'admin', 'ems', 'customer'))
            NOT VALID;
    END IF;
END $$;

-- Unique SePay/review/notification/shipment indexes are installed only by
-- explicit reconcile --apply after duplicate rows are archived/reconciled.

CREATE INDEX IF NOT EXISTS ix_orders_timeline_schema_version
ON orders (timeline_schema_version);
