# Deploy VPS — chuẩn bị dữ liệu & môi trường

## 1. Trên máy dev (trước khi đưa lên VPS)

- **Cài đặt & chạy local:** [HUONG_DAN_CAI_DAT.md](../HUONG_DAN_CAI_DAT.md) (API 8001, Next 3001, `dev-clear-start.bat`).
- **Database:** `pg_dump` PostgreSQL (nếu cần giữ dữ liệu thật) hoặc để app tạo bảng rỗng trên VPS.
- **File:** ảnh sản phẩm đã trên Bunny/CDN; không cần copy `backend/app/static` nếu URL trong DB trỏ CDN.
- **Env:** chuẩn bị `backend/.env` và `frontend/.env.local` production (không commit).

## 2. Trên VPS

### Backup (thủ công + tự động)

**Một lệnh** (database, `.env`, Nginx, SSL, PM2, crontab):

```bash
cd /var/www/188.com.vn
chmod +x deploy/backup-vps.sh   # một lần
bash deploy/backup-vps.sh
```

File nén: `/var/backups/188.com.vn/backup-188-YYYYMMDD-HHMMSS.tar.gz` — **giữ 2 bản mới nhất**.

**Mặc định `pg_dump` bỏ data các bảng cache** — app tự tạo lại khi khách vào / search. Email gửi admin khi backup xong (cần SMTP).

Tải về máy: `scp root@IP_VPS:/var/backups/188.com.vn/backup-188-*.tar.gz ./`

Nên **kết hợp** với **Full Snapshot** trên panel VPS (Sao lưu → + Create Backup).

Lịch tự động: cấu hình trong **Admin → Backup VPS** (lưu DB, API kiểm tra mỗi 60s). **Không cần** thêm dòng crontab backup trừ khi đặt `VPS_BACKUP_SCHEDULER_ENABLED=0` trong `backend/.env`.

**Git (một lần):** Git 2.x có thể báo *divergent branches* khi `git pull`. Trên VPS, trong repo:

```bash
git -C /var/www/188.com.vn config pull.rebase false
```

Sau đó có thể dùng cố định:

```bash
cd /var/www/188.com.vn
git pull origin main
DEPLOY_SKIP_GIT=1 DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
```

(`DEPLOY_SKIP_GIT=1` = không chạy `git` thêm lần nữa trong script, vì đã `git pull` tay; bỏ biến này nếu muốn script tự `git pull`. Script cũng tự: **`.env` pool/TTL**, **index DB**, **swap 8G** — xem mục 2b.)

1. Cài **PostgreSQL**, tạo DB/user (xem `postgres-init.sql.example`). Script **`deploy/update-vps.sh`** (mặc định) sẽ **tự tạo database PostgreSQL** nếu đọc `DATABASE_URL` trỏ tới Postgres (tên DB lấy sau path, vd. `188comvn`), rồi chạy **`init_database_tables()`** (tạo bảng + **`run_migrations()`**). Tuỳ chọn: `DEPLOY_SKIP_DB_INIT=1` (bỏ qua toàn bộ bước DB), `DEPLOY_CREATE_DATABASE=0` (chỉ không gọi `postgres-create-db.sh`, vẫn chạy migrations), `DEPLOY_STRICT_DB_INIT=0` (lỗi DB không dừng script deploy). Nếu log API báo **`FATAL: database "…" does not exist`** mà chưa chạy script: tạo tay hoặc **`sudo bash deploy/postgres-create-db.sh`** (cần `sudo -u postgres`).
2. (Tùy chọn) **Redis** — `redis-notes.txt`.
3. Clone repo, chạy **`bash deploy/prepare-vps.sh`** từ root project (Linux). Script này (và **`deploy/update-vps.sh`**) tự chạy **`deploy/install-playwright-browsers.sh`** — cần cho **lấy thông tin sản phẩm Vipomall** (Playwright). Nếu import Vipomall báo *Executable doesn't exist*: SSH vào VPS và chạy lại `bash deploy/install-playwright-browsers.sh` (hoặc `PLAYWRIGHT_WITH_DEPS=1` nếu thiếu thư viện hệ thống).
4. Lần đầu chạy API: bảng được tạo qua `init_database_tables()` trong `main.py` (và migration trong `app/db/migrations.py`).
5. **Dữ liệu sản phẩm:** đăng nhập admin → Import Excel, hoặc restore `pg_dump`.

**Deploy nhanh (git pull + pip + build) — sau khi clone repo và đã có `deploy/update-vps.sh`:**

```bash
cd /var/www/188.com.vn
chmod +x deploy/update-vps.sh   # chỉ một lần
DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_BUILD_VPS=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
```

Nếu Git báo **divergent branches** hoặc cần **bỏ mọi thay đổi chỉ có trên VPS** và làm khớp hẳn `origin/main`:

```bash
DEPLOY_GIT_SYNC=reset-hard DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
```

**Nginx → Next (Server Actions):** trong mỗi `location` proxy, nên có đủ header: `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`; thêm **`proxy_set_header X-Forwarded-Host $host;`** giúp giảm cảnh báo *Missing origin*. Chi tiết ví dụ: `HUONG_DAN_DEPLOY.md` — Phần 4.

Script sẽ **tự `pm2 restart`** (nếu đã có `188-api` / `188-web`) và **`pm2 save`**, rồi **curl kiểm tra** `:${API_INTERNAL_PORT:-8001}/health` và `:${WEB_INTERNAL_PORT:-3001}/robots.txt` (nhẹ — không SSR trang chủ). Kiểm tra tay: `bash deploy/health-check.sh`. `DEPLOY_RESTART_PM2=0` để chỉ build không restart. `DEPLOY_STRICT_HEALTH=1` để fail (exit≠0) khi không 200.

Lệnh không dùng `pm2 stop all` (tránh làm nanoai). Đặt biến `PM2_API_NAME` / `PM2_WEB_NAME` nếu tên PM2 khác `188-api` / `188-web`.

**Cùng VPS với site khác (vd. nanoai.vn):** nanoai thường chiếm Next **`3000`** — chạy 188 với **`PORT=3001`** (hoặc cổng trống khác). API 188 dùng cổng **không trùng** API đang có (vd. `8001` nếu `8000` là nanoai). Chi tiết bảng cổng và Nginx: **`HUONG_DAN_DEPLOY.md` → Phần 4, mục “Cùng VPS với nanoai.vn”**.

### Health check API trả `000` (không kết nối được)

- Script coi **`curl` → `000`** là không mở được TCP tới cổng đó (khác với HTTP 502/503).
- **`188-web` = 200** mà **`188-api` = 000**: thường do **PM2 vẫn chạy uvicorn cổng cũ** (vd. 8000) trong khi kiểm tra **8001**.
- Sửa một lần trên VPS:

  1. `grep SERVER_PORT /var/www/188.com.vn/backend/.env` → nên là **`SERVER_PORT=8001`** (hoặc khớp `API_INTERNAL_PORT`).
  2. `pm2 show 188-api` → xem **`script args`** / cwd: phải có `--port 8001` **hoặc** biến môi trường tương đương khi khởi động.
  3. Cập nhật lệnh start rồi: `pm2 restart 188-api --update-env` và `pm2 save`.
  4. Xác nhận: `ss -tlnp | grep 8001` và `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/health`.

- Nếu vẫn lỗi: `pm2 logs 188-api --lines 80` (lỗi import DB, thiếu `.env`, v.v.).

### Health check Web trả `000` (API vẫn 200)

- **`000` hoặc `000000`** = không mở được TCP tới Next (process chưa listen hoặc crash loop), không phải HTTP 502.
- **`000000`** trong log deploy cũ: script health check chỉ thử Web **một lần** ngay sau restart (3s) và có thể in đúp `000` khi curl thất bại — bản `update-vps.sh` mới đã chờ tối đa 60s và sửa lỗi in mã.
- **Nguyên nhân hay gặp:**
  1. **`frontend/.next` thiếu** sau build lỗi hoặc deploy bị ngắt.
  2. **PM2 còn cấu hình cũ** (`bash -c … exec npm run start`) — `pm2 restart` **không** đổi script; cần `pm2 delete 188-web` rồi `pm2 start deploy/ecosystem.config.cjs --only 188-web`.
  3. **Cổng 3001 bị chiếm bởi `next-server` mồ côi** (PM2 `errored` nhưng `ss -tlnp | grep 3001` vẫn thấy process) → PM2 không bind được, restart loop. Dọn: `fuser -k 3001/tcp` hoặc `bash deploy/fix-web-health.sh`.
  4. Next chưa kịp bind sau restart (chờ thêm hoặc chạy lại health).
- **Sửa nhanh trên VPS:**

```bash
cd /var/www/188.com.vn
bash deploy/fix-web-health.sh
```

- Kiểm tra tay:

```bash
pm2 list
pm2 show 188-web
ss -tlnp | grep 3001
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3001/
pm2 logs 188-web --lines 80
```

- Nếu thiếu `.next`: `cd frontend && npm ci && npm run build`, rồi `pm2 restart 188-web --update-env`.

### Admin / API báo **504 Gateway Timeout**

- **Nguyên nhân hay gặp:** Nginx `proxy_read_timeout` mặc định (~60s) nhỏ hơn thời gian FastAPI chờ **PostgreSQL** (pool hoặc query chậm) → Nginx trả 504 trước khi API xong.
- **Kiểm tra timeout hiện tại trên VPS:**

```bash
sudo nginx -T 2>/dev/null | grep -E 'server_name|location |proxy_read_timeout|proxy_send_timeout'
```

- **Giá trị khuyến nghị** (file mẫu `deploy/nginx-site-188.com.vn.conf.example`):

| Location | `proxy_read_timeout` | `proxy_send_timeout` | Ghi chú |
|----------|----------------------|----------------------|---------|
| `/api/v1/import-export/import/` | **3600s** | **3600s** | Upload + import Excel lớn |
| `/api/v1/import-export/export/` | **900s** | **900s** | Export ~30k SP |
| `location /api/` (còn lại) | **900s** | **900s** | Trước đây thường chỉ **180s** → export dễ 504 |
| `location /` → Next :3001 | **900s** | **900s** | Mặc định nginx ~60s nếu không khai báo |

- **Sửa:** Đồng bộ VPS với mẫu trên (hoặc copy cả file), rồi:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

- **Đồng thời:** Trên VPS chia sẻ, **không** tăng pool quá cao — dùng `bash deploy/tune-db-vps.sh` (mặc định `8` + `12` overflow). Pool lớn → nhiều query COUNT song song → Postgres treo. Xem log `QueuePool` / `TimeoutError`.

## 2b. Tuning DB — VPS chia sẻ (nanoai + 188 + Postgres local)

Không đổi tính năng/UI; chỉ giảm tải DB:

| Việc | Mặc định mới | Ghi chú |
|------|--------------|---------|
| Connection pool | `8` + overflow `12` | Tối đa ~20 conn / `188-api` |
| Cache menu `/categories/from-products` | 300s | Trước 60s |
| Cache `/danh-muc` catalog-tiles | 300s | Trước 120s |
| Index | `ix_products_active_category_id` | Tự tạo khi API migrate |

**Tự động:** `deploy/update-vps.sh` đã gọi `tune-db-vps.sh` sau bước init DB (pool `.env`, index, swap 8G). Tắt: `DEPLOY_SKIP_DB_TUNING=1` hoặc chỉ tắt swap: `DEPLOY_SKIP_SWAP=1`.

**Chỉ tuning (không build):**

```bash
cd /var/www/188.com.vn
bash deploy/tune-db-vps.sh
pm2 restart 188-api --update-env && pm2 save
```

Tùy chọn trong `backend/.env`: `CATEGORY_MENU_TREE_TTL_SECONDS`, `CATEGORY_CATALOG_TILES_TTL_SECONDS` (giây).

**Theo dõi:** `sudo -u postgres psql -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;"` — `188comvn` nên **< 15** khi bình thường.

## 3. Crontab VPS

File mẫu: **`deploy/crontab.188.com.vn.example`** (khuyến mãi, tra EMS, dọn temp việt hóa ảnh).

**Cài lần đầu** (đọc file mẫu, thay secret + domain, ghi crontab):

```bash
cd /var/www/188.com.vn
sed -e 's/YOUR_CRON_SECRET/'"$(grep -E '^CRON_SECRET=' backend/.env | cut -d= -f2-)"'/g' \
    -e 's/YOUR_API_HOST/188.com.vn/g' \
    deploy/crontab.188.com.vn.example | crontab -
crontab -l
```

**Đã có crontab** — chỉ thêm dòng dọn temp: `crontab -e`, dán dòng cuối trong file mẫu (Chủ nhật 3:00).

## 4. Tài liệu liên quan

- `../HUONG_DAN_DEPLOY.md` — biến môi trường, build, domain.
- `../DEPLOY_READINESS.md` — checklist tổng thể.
- `../backend/.env.example`, `../frontend/.env.example` — đầy đủ khóa cấu hình.
