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

**Deploy nhanh (git pull + pip + build) — sau khi clone repo và đã có `deploy/update-vps.sh`:**

```bash
cd /var/www/188.com.vn
chmod +x deploy/update-vps.sh   # chỉ một lần
DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_BUILD_VPS=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
```

**Nginx → Next (Server Actions):** trong mỗi `location` proxy, nên có đủ header: `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`; thêm **`proxy_set_header X-Forwarded-Host $host;`** giúp giảm cảnh báo *Missing origin*. Chi tiết ví dụ: `HUONG_DAN_DEPLOY.md` — Phần 4.

Script sẽ **tự `pm2 restart`** (nếu đã có `188-api` / `188-web`) và **`pm2 save`**, rồi **curl kiểm tra** `:${API_INTERNAL_PORT:-8001}/health` và `:${WEB_INTERNAL_PORT:-3001}/`. `DEPLOY_RESTART_PM2=0` để chỉ build không restart. `DEPLOY_STRICT_HEALTH=1` để fail (exit≠0) khi không 200.

Lệnh không dùng `pm2 stop all` (tránh làm nanoai). Đặt biến `PM2_API_NAME` / `PM2_WEB_NAME` nếu tên PM2 khác `188-api` / `188-web`.

**Cùng VPS với site khác (vd. nanoai.vn):** nanoai thường chiếm Next **`3000`** — chạy 188 với **`PORT=3001`** (hoặc cổng trống khác). API 188 dùng cổng **không trùng** API đang có (vd. `8001` nếu `8000` là nanoai). Chi tiết bảng cổng và Nginx: **`HUONG_DAN_DEPLOY.md` → Phần 4, mục “Cùng VPS với nanoai.vn”**.

## 3. Tài liệu liên quan

- `../HUONG_DAN_DEPLOY.md` — biến môi trường, build, domain.
- `../DEPLOY_READINESS.md` — checklist tổng thể.
- `../backend/.env.example`, `../frontend/.env.example` — đầy đủ khóa cấu hình.
