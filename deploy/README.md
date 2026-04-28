# Deploy VPS — chuẩn bị dữ liệu & môi trường

## 1. Trên máy dev (trước khi đưa lên VPS)

- **Database:** `pg_dump` PostgreSQL (nếu cần giữ dữ liệu thật) hoặc để app tạo bảng rỗng trên VPS.
- **File:** ảnh sản phẩm đã trên Bunny/CDN; không cần copy `backend/app/static` nếu URL trong DB trỏ CDN.
- **Env:** chuẩn bị `backend/.env` và `frontend/.env.local` production (không commit).

## 2. Trên VPS

1. Cài **PostgreSQL**, tạo DB/user (xem `postgres-init.sql.example`).
2. (Tùy chọn) **Redis** — `redis-notes.txt`.
3. Clone repo, chạy **`bash deploy/prepare-vps.sh`** từ root project (Linux).
4. Lần đầu chạy API: bảng được tạo qua `init_database_tables()` trong `main.py` (và migration trong `app/db/migrations.py`).
5. **Dữ liệu sản phẩm:** đăng nhập admin → Import Excel, hoặc restore `pg_dump`.

## 3. Tài liệu liên quan

- `../HUONG_DAN_DEPLOY.md` — biến môi trường, build, domain.
- `../DEPLOY_READINESS.md` — checklist tổng thể.
- `../backend/.env.example`, `../frontend/.env.example` — đầy đủ khóa cấu hình.
