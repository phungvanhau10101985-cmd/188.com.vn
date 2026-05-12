-- Gỡ cột sale_price nếu đã thêm trước đó (giá sale feed tính từ env CATALOG_SALE_*, không lưu DB).
ALTER TABLE products DROP COLUMN IF EXISTS sale_price;
