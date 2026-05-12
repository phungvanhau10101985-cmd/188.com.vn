-- Hai cột mới: tên tiếng Trung, shop Trung Quốc (Excel AM–AN). Chạy trên PostgreSQL khi deploy.
ALTER TABLE products ADD COLUMN IF NOT EXISTS chinese_name VARCHAR(500);
ALTER TABLE products ADD COLUMN IF NOT EXISTS shop_name_chinese VARCHAR(200);
