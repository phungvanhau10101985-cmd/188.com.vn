-- Migration: Thêm cột user_id vào bảng cart_items
-- Tạo ngày: 2026-01-29
-- Mô tả: Thêm cột user_id và foreign key constraint để đồng bộ với model hiện tại

BEGIN TRANSACTION;

-- 1. Thêm cột user_id (cho phép NULL tạm thời)
ALTER TABLE cart_items ADD COLUMN user_id INTEGER;

-- 2. Cập nhật giá trị user_id từ bảng carts (nếu có quan hệ)
UPDATE cart_items 
SET user_id = (
    SELECT c.user_id 
    FROM carts c 
    WHERE c.id = cart_items.cart_id
)
WHERE cart_items.user_id IS NULL;

-- 3. Thêm foreign key constraint
CREATE INDEX IF NOT EXISTS ix_cart_items_user_id ON cart_items (user_id);

-- 4. Đánh dấu NOT NULL sau khi đã có dữ liệu (nếu muốn)
-- ALTER TABLE cart_items ALTER COLUMN user_id SET NOT NULL;

COMMIT;