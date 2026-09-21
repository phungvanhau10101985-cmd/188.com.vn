-- Additive schema needed by the dry-run-first parity reconciler.
-- No existing business data is changed by this migration.

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS warehouse_reserved INTEGER NOT NULL DEFAULT 0;

ALTER TABLE order_items
    ADD COLUMN IF NOT EXISTS warehouse_stock_additive BOOLEAN NOT NULL DEFAULT false;

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
        WHERE conname = 'ck_products_warehouse_reserved_nonnegative'
    ) THEN
        ALTER TABLE products
            ADD CONSTRAINT ck_products_warehouse_reserved_nonnegative
            CHECK (warehouse_reserved >= 0) NOT VALID;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname IN (
            'ck_order_shipment_events_actor_type',
            'order_shipment_events_actor_type_check'
        )
    ) THEN
        ALTER TABLE order_shipment_events
            ADD CONSTRAINT ck_order_shipment_events_actor_type
            CHECK (actor_type IN ('system', 'cron', 'admin', 'ems', 'customer'))
            NOT VALID;
    END IF;
END $$;

-- The unique shipment idempotency index is installed by explicit reconcile
-- --apply after duplicate keys have been rewritten deterministically.

CREATE INDEX IF NOT EXISTS ix_orders_timeline_schema_version
ON orders (timeline_schema_version);
