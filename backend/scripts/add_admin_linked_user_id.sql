-- Chạy một lần trên DB production/staging (PostgreSQL khuyến nghị IF NOT EXISTS để chạy lại an toàn).
-- SQLite (tuỳ chọn): sqlite3 your.db < scripts/add_admin_linked_user_id.sql

ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS linked_user_id INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS ix_admin_users_linked_user_id ON admin_users(linked_user_id);

-- PostgreSQL — FK (tuỳ chọn; bảng users phải tồn tại):
-- ALTER TABLE admin_users DROP CONSTRAINT IF EXISTS fk_admin_linked_user;
-- ALTER TABLE admin_users ADD CONSTRAINT fk_admin_linked_user FOREIGN KEY (linked_user_id) REFERENCES users(id) ON DELETE SET NULL;
