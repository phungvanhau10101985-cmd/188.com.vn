-- Bảng job bản địa hóa ảnh (nếu chưa có — SQLAlchemy create_all cũng tạo được).
-- PostgreSQL / SQLite tương thích cơ bản qua create_all trên startup.

CREATE TABLE IF NOT EXISTS image_localization_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    phase VARCHAR(64),
    message TEXT,
    payload JSON,
    current INTEGER DEFAULT 0,
    total INTEGER,
    done INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    percent REAL,
    current_product_id VARCHAR(255),
    cancel_requested BOOLEAN NOT NULL DEFAULT 0,
    queue_product_ids JSON,
    processed_product_ids JSON,
    job_queue_truncated BOOLEAN DEFAULT 0,
    recent_results JSON,
    skipped_product_reports JSON,
    language VARCHAR(20),
    force BOOLEAN DEFAULT 0,
    dry_run BOOLEAN DEFAULT 0,
    gemini_mode VARCHAR(20),
    local_image_only BOOLEAN DEFAULT 0,
    resume_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_image_localization_jobs_status ON image_localization_jobs (status);
