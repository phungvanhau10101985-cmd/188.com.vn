# Đánh giá sẵn sàng deploy – 188.com.vn

**Cập nhật:** 02/2025

---

## Tóm tắt

| Hạng mục | Trạng thái | Ghi chú |
|----------|------------|---------|
| **Backend** | ✅ Sẵn sàng | Cấu hình .env đúng là có thể chạy production |
| **Bảo mật** | ✅ Đã xử lý | Xem [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) |
| **Frontend build** | ⚠️ Cần xử lý | Lỗi resolve `antd` khi `npm run build` – xem mục 3 |
| **Cấu hình production** | 📋 Checklist | Cần set đủ biến môi trường – xem mục 2 |

**Kết luận:** Backend và bảo mật đã sẵn sàng. Trước khi deploy cần: (1) cấu hình đủ .env theo checklist, (2) sửa build frontend (antd) hoặc tạm bỏ antd ở trang checkout.

---

## 1. Backend – Sẵn sàng

- FastAPI, CORS từ env, JWT từ config, docs có thể tắt.
- Database: hỗ trợ PostgreSQL (khuyến nghị production) và SQLite (dev).
- File `.env.example` có đủ biến cần thiết.

**Chạy production (ví dụ):**
```bash
cd backend
# Tạo .env từ .env.example và điền giá trị
uvicorn main:app --host 0.0.0.0 --port 8000
# Không dùng --reload trên production
```

---

## 2. Checklist cấu hình trước khi deploy

### Backend (`.env` trong thư mục `backend/`)

| Biến | Bắt buộc | Ghi chú |
|------|----------|---------|
| `SECRET_KEY` | ✅ | Chuỗi bí mật mạnh (vd: `openssl rand -hex 32`) |
| `BACKEND_CORS_ORIGINS` | ✅ | Domain frontend, ví dụ: `https://188.com.vn,https://www.188.com.vn` |
| `DATABASE_URL` | ✅ | PostgreSQL cho production, ví dụ: `postgresql://user:pass@host:5432/dbname` |
| `ENVIRONMENT` | ✅ | `production` |
| `DEBUG` | ✅ | `False` |
| `DISABLE_DOCS` | Khuyến nghị | `true` để tắt Swagger/ReDoc |
| Các key Zalo/Firebase/OpenAI/SMTP | Theo tính năng | Chỉ dùng giá trị từ .env, không để default nhạy cảm trong code |

### Frontend (`.env.local` hoặc biến môi trường trên host build)

| Biến | Bắt buộc | Ghi chú |
|------|----------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | ✅ | URL API production, ví dụ: `https://api.188.com.vn/api/v1` – **không dùng localhost** khi deploy |
| `NEXT_PUBLIC_DOMAIN` / `NEXT_PUBLIC_SITE_URL` | Khuyến nghị | Domain site, ví dụ: `https://188.com.vn` |

### Hạ tầng

- Backend và frontend chạy qua **HTTPS** (reverse proxy: Nginx, Caddy, v.v.).
- Không bật debug/reload trên server production.
- Phân quyền file `.env` hợp lý (chỉ process app đọc được).

---

## 3. Frontend build – Đã xử lý

Trang checkout **đã được viết lại** dùng Tailwind/HTML thuần, **không còn dùng Ant Design**. Khi chạy `npm run build` trong `frontend/`, build sẽ không còn lỗi `antd/lib`.

- Nếu trên máy bạn vẫn báo lỗi **EPERM / spawn**: thử chạy CMD/PowerShell **với quyền Administrator** hoặc tạm tắt phần mềm diệt virus đang chặn Node.
- Hướng dẫn từng bước deploy: xem **[HUONG_DAN_DEPLOY.md](./HUONG_DAN_DEPLOY.md)**.

---

## 4. Các tài liệu liên quan

- **[SECURITY_AUDIT.md](./SECURITY_AUDIT.md)** – Bảo mật, checklist bảo mật khi deploy, rate limiting, log.
- **Backend:** `backend/.env.example` – Mẫu biến môi trường.
- **Frontend:** `frontend/.env.example` – Mẫu biến môi trường (cần thêm dòng production cho `NEXT_PUBLIC_API_BASE_URL`).

---

## 5. Lệnh kiểm tra nhanh

```bash
# Backend: kiểm tra chạy được (sau khi có .env)
cd backend && python -c "from app.core.config import settings; print('OK' if settings.SECRET_KEY else 'FAIL')"

# Frontend: kiểm tra build (sau khi sửa lỗi antd nếu có)
cd frontend && npm run build
```

Sau khi hoàn thành checklist mục 2 và sửa build frontend (mục 3), dự án có thể triển khai lên môi trường production.

---

## 6. Chuẩn bị VPS + dữ liệu (PostgreSQL / Redis / seed)

Trong repo có thư mục **`deploy/`**:

| File | Mục đích |
|------|-----------|
| **`deploy/README.md`** | Checklist ngắn: DB trên VPS, Bunny/CDN, import dữ liệu |
| **`deploy/prepare-vps.sh`** | Ubuntu/Debian: `python3 -venv`, `pip install`, gọi `init_database_tables()` trong `main.py`, tùy chọn `npm run build` |
| **`deploy/postgres-init.sql.example`** | Mẫu `CREATE DATABASE` / user — chỉnh rồi áp vào PostgreSQL server |
| **`deploy/redis-notes.txt`** | Gợi ý cài Redis nếu dùng `REDIS_URL` trong `.env` |

**Luồng dữ liệu:**

1. Trên VPS: tạo PostgreSQL + user/database (hoặc dịch vụ managed) → **`DATABASE_URL`** trong `backend/.env`.
2. Chạy **`bash deploy/prepare-vps.sh`** (Linux) hoặc thủ công: `cd backend` → venv → pip → `python -c "from main import init_database_tables; init_database_tables()"`.
3. Dữ liệu sản phẩm/khách: **import Excel** trong admin, hoặc **`pg_restore`** / **`pg_dump`** nếu mang DB từ máy dev.
4. **Redis** tùy chọn; **Bunny** (`BUNNY_*`, `NEXT_PUBLIC_CDN_URL`) phải khớp Pull Zone khi deploy ảnh.
5. **HTTPS:** Nginx/Caddy phía trước UVicorn (API) và Next.js.
