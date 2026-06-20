-- Bảng hàng đợi + log chống trùng email phản hồi câu hỏi/đánh giá.
-- SQLAlchemy create_all() trên startup cũng tạo được; script này để chạy tay khi cần.

CREATE TABLE IF NOT EXISTS pending_product_reply_emails (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    slot VARCHAR(20) NOT NULL DEFAULT '',
    send_after TIMESTAMPTZ NOT NULL,
    exclude_replier_user_id INTEGER NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_pending_product_reply_email UNIQUE (kind, entity_id, slot)
);

CREATE INDEX IF NOT EXISTS ix_pending_product_reply_emails_send_after
    ON pending_product_reply_emails (send_after);

CREATE TABLE IF NOT EXISTS product_reply_email_sent_logs (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    slot VARCHAR(20) NOT NULL DEFAULT '',
    content_fingerprint VARCHAR(64) NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_product_reply_email_sent_logs_lookup
    ON product_reply_email_sent_logs (kind, entity_id, slot, content_fingerprint, sent_at);
