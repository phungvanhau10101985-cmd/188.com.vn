-- Chạy một lần trên DB production/staging (SQLite hoặc PostgreSQL).
-- SQLite: sqlite3 your.db < scripts/add_admin_linked_user_id.sql

ALTER TABLE admin_users ADD COLUMN linked_user_id INTEGER;

-- SQLite: UNIQUE cho phép nhiều NULL
CREATE UNIQUE INDEX IF NOT EXISTS ix_admin_users_linked_user_id ON admin_users(linked_user_id);

-- PostgreSQL (tuỳ chọn — nếu muốn FK rõ ràng sau khi đã có cột):
-- ALTER TABLE admin_users ADD CONSTRAINT fk_admin_linked_user FOREIGN KEY (linked_user_id) REFERENCES users(id) ON DELETE SET NULL;
