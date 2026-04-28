# Danh sách thông tin cần điền (.env)

Copy file `.env.example` thành `.env` (backend) hoặc `.env.local` (frontend), rồi **thay giá trị** theo bảng dưới.

---

## 1. Backend (`backend/.env`)

### Bắt buộc khi deploy production

| Biến | Ý nghĩa | Ví dụ / Cách lấy |
|------|--------|-------------------|
| **SECRET_KEY** | Chuỗi bí mật để ký JWT, mã hóa. Phải đủ dài và ngẫu nhiên. | Tạo bằng lệnh: `openssl rand -hex 32` (chạy trong CMD/PowerShell). Hoặc tự đặt một chuỗi dài ít nhất 32 ký tự. |
| **BACKEND_CORS_ORIGINS** | Các domain được phép gọi API (frontend của bạn). | `https://188.com.vn,https://www.188.com.vn` (thay bằng domain thật của bạn, nhiều domain cách nhau bằng dấu phẩy). |
| **DATABASE_URL** | Chuỗi kết nối PostgreSQL. | `postgresql://tên_user:mật_khẩu@host:5432/tên_database` – lấy từ Supabase / Railway / Neon / VPS sau khi tạo database. |
| **ENVIRONMENT** | Môi trường chạy. | `production` |
| **DEBUG** | Bật/tắt chế độ debug. | `False` |

### Tùy chọn (chỉ điền nếu dùng tính năng đó)

| Biến | Ý nghĩa | Khi nào cần |
|------|--------|-------------|
| **DISABLE_DOCS** | Tắt Swagger/ReDoc trên production. | Khuyến nghị: đặt `true` để ẩn trang /docs, /redoc. |
| **PROJECT_NAME** | Tên dự án. | Mặc định `188-com-vn`, có thể giữ. |
| **SERVER_NAME** | Tên domain backend (hiển thị, metadata). | Ví dụ: `api.188.com.vn` |
| **DATABASE_POOL_SIZE**, **DATABASE_MAX_OVERFLOW**, **DATABASE_POOL_RECYCLE** | Cấu hình pool kết nối DB. | Có thể để mặc định (5, 10, 3600). |

### Chỉ điền khi bật OTP đăng ký (Zalo + fallback Firebase)

Luồng OTP trong dự án: **Zalo** gửi trước; nếu Zalo lỗi thì **Firebase** (webhook) gửi thay.

| Biến | Ý nghĩa | Khi nào cần |
|------|--------|-------------|
| **ZALO_OA_ID**, **ZALO_OA_SECRET**, **ZALO_OA_ACCESS_TOKEN**, **ZALO_REFRESH_TOKEN** | Zalo Official Account – lấy từ [Zalo Developer](https://developers.zalo.me) | Gửi OTP qua Zalo khi đăng ký |
| **ZALO_TEMPLATE_REGISTER** | ID template tin nhắn OTP đăng ký (vd: 304254) | Cùng với Zalo OA |
| **FIREBASE_OTP_WEBHOOK_URL** | URL Cloud Function / webhook nhận `POST` body `{"phone":"09xx","otp":"123456"}` để gửi SMS OTP | Fallback khi Zalo gửi thất bại. Để trống = chỉ log OTP ra console (dev/test) |

- **Firebase (Auth/Realtime):** `FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, `FIREBASE_CLIENT_EMAIL`, … – chỉ cần nếu dùng Firebase SDK trực tiếp; fallback OTP trong code chỉ cần **FIREBASE_OTP_WEBHOOK_URL** (hoặc không cấu hình để dùng log console).
- **Email (gửi mail):** `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`.
- **AI (OpenAI/DeepSeek):** `OPENAI_API_KEY` hoặc `DEEPSEEK_API_KEY` – lấy từ trang API tương ứng.

Nếu **không dùng** OTP Zalo/Firebase, Email, hay AI thì **không cần** điền các biến đó; code có giá trị mặc định hoặc tính năng sẽ tắt.

---

## 2. Frontend (`frontend/.env.local` hoặc biến môi trường khi deploy)

### Bắt buộc khi deploy production

| Biến | Ý nghĩa | Ví dụ |
|------|--------|--------|
| **NEXT_PUBLIC_API_BASE_URL** | URL API backend (đầy đủ đến `/api/v1`). | `https://api.188.com.vn/api/v1` – thay bằng domain backend thật của bạn. **Không dùng** `localhost` khi deploy. |

### Tùy chọn

| Biến | Ý nghĩa | Ví dụ |
|------|--------|--------|
| **NEXT_PUBLIC_DOMAIN** | Domain website (frontend). | `https://188.com.vn` |
| **NEXT_PUBLIC_SITE_URL** | URL gốc của site. | `https://188.com.vn` |

---

## Tóm tắt nhanh

**Backend – tối thiểu khi deploy:**

- `SECRET_KEY` = chuỗi bí mật mạnh (tự tạo hoặc `openssl rand -hex 32`)
- `BACKEND_CORS_ORIGINS` = domain frontend (vd: `https://188.com.vn,https://www.188.com.vn`)
- `DATABASE_URL` = chuỗi kết nối PostgreSQL
- `ENVIRONMENT=production`
- `DEBUG=False`

**Frontend – tối thiểu khi deploy:**

- `NEXT_PUBLIC_API_BASE_URL` = URL backend (vd: `https://api.188.com.vn/api/v1`)

Các biến khác chỉ cần điền khi bạn dùng tính năng tương ứng (Zalo, Firebase, Email, AI, v.v.).
