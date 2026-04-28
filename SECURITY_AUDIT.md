# Báo cáo kiểm tra bảo mật – 188-com-vn

**Ngày kiểm tra:** 02/02/2025  
**Mục đích:** Đánh giá sẵn sàng bảo mật trước khi deploy production.

---

## Tóm tắt

| Hạng mục | Trạng thái | Ghi chú |
|----------|------------|---------|
| Secrets / biến môi trường | ✅ Đã cải thiện | SECRET_KEY, CORS, OPENAI_KEY đã chỉnh; cần cấu hình .env khi deploy |
| CORS | ✅ Đã sửa | Dùng `BACKEND_CORS_ORIGINS` từ .env, không còn `*` |
| JWT / Auth | ✅ Đã sửa | JWT dùng SECRET_KEY từ config; mật khẩu hash bcrypt |
| Admin routes | ✅ OK | Bảo vệ bằng `get_current_admin` |
| SQL injection | ✅ OK | Dùng ORM/SQLAlchemy; raw SQL chỉ trong migration (tham số hóa) |
| Tài liệu API (docs) | ✅ Có tùy chọn | Có thể tắt bằng `DISABLE_DOCS=true` |
| Rate limiting | ⚠️ Cấu hình có, chưa áp dụng | Config có RATE_LIMIT_* nhưng chưa thấy middleware trong main |
| Frontend API URL | ⚠️ Cần kiểm tra | Production cần `NEXT_PUBLIC_API_BASE_URL` đúng domain |
| Log nhạy cảm | ⚠️ Nên giảm | Frontend còn `console.log` với URL/header API |

---

## 1. Đã xử lý trong code

### 1.1. SECRET_KEY và JWT (`backend/app/core/security.py`)

- **Trước:** Hardcode `SECRET_KEY = "your-secret-key-change-in-production"`.
- **Sau:** Dùng `settings.SECRET_KEY` từ `app.core.config`; thêm `_get_secret_key()` và báo lỗi rõ ràng nếu SECRET_KEY chưa được cấu hình (placeholder hoặc trống).
- **Khi deploy:** Bắt buộc đặt `SECRET_KEY` trong `.env` (chuỗi ngẫu nhiên đủ mạnh, ví dụ 64 ký tự hex).

### 1.2. CORS (`backend/main.py`)

- **Trước:** `allow_origins=["*"]` – mọi domain đều gọi được API.
- **Sau:** Dùng `settings.BACKEND_CORS_ORIGINS` (đọc từ biến môi trường `BACKEND_CORS_ORIGINS`).
- **Khi deploy:** Trong `.env` backend, đặt ví dụ:  
  `BACKEND_CORS_ORIGINS=https://188.com.vn,https://www.188.com.vn`

### 1.3. Tài liệu API (Swagger/ReDoc)

- Có thể tắt hoàn toàn khi deploy bằng biến môi trường:  
  `DISABLE_DOCS=true`  
- Khi đó `/docs`, `/redoc`, `/openapi.json` sẽ không còn phục vụ.

### 1.4. OPENAI_API_KEY (`backend/app/core/config.py`)

- **Trước:** Có default là một chuỗi trông giống API key thật trong code.
- **Sau:** Default là `""`; nếu dùng tính năng AI thì bắt buộc cấu hình `OPENAI_API_KEY` trong `.env`.

### 1.5. File .env không commit

- `backend/.gitignore` và `frontend/.gitignore` đã có `.env`, `.env.local`, ... → không bị đẩy lên git.

---

## 2. Checklist trước khi deploy

### Backend

- [ ] Tạo/copy `.env` từ `.env.example`, **không** commit file `.env` thật.
- [ ] Đặt `SECRET_KEY` mạnh (ví dụ: `openssl rand -hex 32`).
- [ ] Đặt `BACKEND_CORS_ORIGINS` đúng domain frontend production (phân cách bằng dấu phẩy).
- [ ] Đặt `DATABASE_URL` cho PostgreSQL (production không nên dùng SQLite mặc định).
- [ ] Đặt `ENVIRONMENT=production`, `DEBUG=False`.
- [ ] Nếu dùng OTP/Email: cấu hình SMTP (SMTP_USERNAME, SMTP_PASSWORD, ...).
- [ ] Nếu dùng Zalo/Firebase: đặt tất cả ZALO_*, FIREBASE_* trong `.env`, **không** dựa vào default trong code (tránh lộ key trong repo).
- [ ] Nếu dùng AI: đặt `OPENAI_API_KEY` và/hoặc `DEEPSEEK_API_KEY` trong `.env`.
- [ ] Cân nhắc đặt `DISABLE_DOCS=true` để tắt Swagger/ReDoc trên production.

### Frontend

- [ ] Tạo/copy `.env.local` (hoặc biến môi trường trên host) từ `.env.example`.
- [ ] Đặt `NEXT_PUBLIC_API_BASE_URL` trỏ tới URL API production (ví dụ `https://api.188.com.vn/api/v1`), **không** dùng `localhost` khi deploy.
- [ ] Đặt `NEXT_PUBLIC_DOMAIN` / `NEXT_PUBLIC_SITE_URL` đúng domain site.

### Hạ tầng / vận hành

- [ ] Chạy backend qua HTTPS (reverse proxy: Nginx/Caddy, v.v.).
- [ ] Không mở cổng debug (vd. `reload=True`, debugger) trên môi trường production.
- [ ] Giới hạn quyền đọc file `.env` (chỉ process app đọc được).

---

## 3. Khuyến nghị thêm

### Rate limiting

- Trong `config` đã có `RATE_LIMIT_ENABLED`, `RATE_LIMIT_REQUESTS_PER_MINUTE`, `RATE_LIMIT_OTP_PER_HOUR`.
- Hiện chưa thấy middleware rate limit được gắn vào app trong `main.py`.
- Nên: thêm middleware (ví dụ `slowapi` hoặc custom) đọc các biến này và áp dụng giới hạn request/OTP để chống brute-force và lạm dụng API.

### Log và debug

- Frontend: giảm hoặc tắt `console.log` có thông tin request/header (ví dụ trong `api-client.ts`) trên bản build production (có thể dùng biến môi trường hoặc strip log khi build).
- Backend: đảm bảo không log token, mật khẩu, hoặc thông tin cá nhân ra file/console.

### Zalo / Firebase default trong code

- Trong `config.py` vẫn còn default dài cho ZALO (OA_SECRET, ACCESS_TOKEN, REFRESH_TOKEN) và FIREBASE (PRIVATE_KEY, API_KEY, ...).
- Rủi ro: nếu repo public hoặc bị lộ, key mặc định có thể bị dùng.
- Khuyến nghị: với production, không dùng default nhạy cảm; đặt toàn bộ trong `.env` và có thể đổi default trong code thành `""` cho các biến secret, sau đó bắt buộc cấu hình qua env.

---

## 4. Kết luận

- Các điểm quan trọng cho deploy (SECRET_KEY, CORS, JWT từ config, ẩn docs, không để API key mặc định trong code) đã được xử lý hoặc có hướng cấu hình rõ ràng.
- Sau khi hoàn thành checklist ở mục 2 và cân nhắc rate limiting + log (mục 3), dự án có thể coi là **đã đảm bảo mức bảo mật tối thiểu để deploy**, với điều kiện cấu hình đúng `.env` và môi trường production (HTTPS, không debug, bảo vệ file .env).

Nếu bạn muốn, bước tiếp theo có thể là: thêm rate limit middleware và cập nhật `.env.example` đầy đủ biến cho production.
