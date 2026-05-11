-- Ảnh hướng dẫn chọn size theo danh mục cấp 1 (URL CDN Bunny sau khi sinh bằng Gemini).
ALTER TABLE categories ADD COLUMN IF NOT EXISTS size_guide_image_url VARCHAR(800);
