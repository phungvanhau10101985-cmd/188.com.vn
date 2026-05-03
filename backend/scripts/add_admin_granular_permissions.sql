-- Thêm cột quyền theo mục (JSON array string keys — xem backend/app/core/admin_permissions.py ALLOWED_MODULE_KEYS).
-- PostgreSQL:
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS granular_permissions JSONB;

-- SQLite (không có JSONB — dùng TEXT chứa JSON; hoặc bỏ qua nếu chỉ dev và để Alembic/SQLAlchemy tự tạo):
-- ALTER TABLE admin_users ADD COLUMN granular_permissions TEXT;
