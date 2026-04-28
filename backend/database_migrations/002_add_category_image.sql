-- ==================================================
-- MIGRATION: Thêm cột image vào bảng categories
-- Version: 1.0
-- Created: 2026-01-28
-- Author: System Migration
-- Status: READY
-- ==================================================

-- BẢN MIGRATION NÀY SẼ:
-- 1. Kiểm tra xem cột 'image' đã tồn tại chưa
-- 2. Thêm cột 'image' nếu chưa có
-- 3. Cập nhật giá trị mặc định cho dữ liệu hiện có
-- 4. Kiểm tra và xác nhận kết quả

-- ==================================================
-- PHẦN 1: THÊM CỘT IMAGE
-- ==================================================

-- SQLite không hỗ trợ ADD COLUMN IF NOT EXISTS trực tiếp
-- Sẽ xử lý logic này trong Python script

-- Câu lệnh thêm cột (chỉ thực thi khi chưa có)
-- ALTER TABLE categories ADD COLUMN image VARCHAR(500);

-- Câu lệnh cập nhật giá trị mặc định
-- UPDATE categories SET image = '' WHERE image IS NULL;

-- ==================================================
-- PHẦN 2: KIỂM TRA KẾT QUẢ
-- ==================================================

-- Sau khi migration, có thể chạy các câu lệnh kiểm tra:

-- 1. Xem cấu trúc bảng:
-- PRAGMA table_info(categories);

-- 2. Xem dữ liệu mẫu:
-- SELECT id, name, slug, image FROM categories LIMIT 5;

-- 3. Đếm số bản ghi:
-- SELECT COUNT(*) as total_categories FROM categories;

-- ==================================================
-- PHẦN 3: ROLLBACK SCRIPT (nếu cần)
-- ==================================================

-- Nếu cần rollback (chỉ dùng khi cần thiết):
-- ALTER TABLE categories DROP COLUMN image;