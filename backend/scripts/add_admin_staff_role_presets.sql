-- Bảng preset mục + CRUD cho 3 vai trò NV (order_manager, product_manager, content_manager).
-- SQLAlchemy create_all() thường đã tạo bảng từ model AdminStaffRolePreset; script này để chạy tay khi cần.

-- PostgreSQL
CREATE TABLE IF NOT EXISTS admin_staff_role_presets (
  id SERIAL PRIMARY KEY,
  role VARCHAR(32) NOT NULL UNIQUE,
  modules JSONB NOT NULL DEFAULT '[]'::jsonb,
  module_crud JSONB NOT NULL DEFAULT '{}'::jsonb
);
