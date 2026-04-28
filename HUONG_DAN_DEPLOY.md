# Hướng dẫn deploy – 188.com.vn

Chỉ **bạn** mới làm được các bước dưới (tạo file .env, chọn server, mua domain). Phần code đã được chỉnh để build chạy được; bạn chỉ cần làm đúng từng bước.

---

## Phần 1: Những việc BẠN cần làm (không thể làm thay)

### Bước 1 – Backend: Tạo file `.env`

1. Vào thư mục **backend**.
2. Copy file `.env.example` thành `.env` (nếu chưa có).
3. Mở `.env` và **điền/sửa** các dòng sau (thay giá trị mẫu bằng giá trị thật của bạn):

```env
# BẮT BUỘC – thay bằng chuỗi bí mật mạnh (ví dụ chạy trong CMD: openssl rand -hex 32)
SECRET_KEY=your-secret-key-change-in-production

# BẮT BUỘC – domain frontend thật, cách nhau bởi dấu phẩy
BACKEND_CORS_ORIGINS=https://188.com.vn,https://www.188.com.vn

# BẮT BUỘC – database production (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:5432/ten_database

# Production
ENVIRONMENT=production
DEBUG=False

# Tùy chọn: tắt Swagger/ReDoc trên production
DISABLE_DOCS=true
```

- **SECRET_KEY:** Bạn tự tạo (hoặc dùng lệnh `openssl rand -hex 32`).
- **BACKEND_CORS_ORIGINS:** Domain website của bạn (nơi frontend chạy).
- **DATABASE_URL:** Thông tin PostgreSQL bạn thuê (host, user, password, tên database).

Không commit file `.env` lên Git.

---

### Bước 2 – Frontend: Cấu hình biến môi trường khi build/deploy

1. Trong thư mục **frontend**, tạo hoặc sửa file **`.env.local`** (hoặc cấu hình env trên nền tảng deploy).
2. **Khi deploy production**, đặt:

```env
# URL API backend thật – KHÔNG dùng localhost
NEXT_PUBLIC_API_BASE_URL=https://api.188.com.vn/api/v1

# Domain site (tùy chọn)
NEXT_PUBLIC_DOMAIN=https://188.com.vn
NEXT_PUBLIC_SITE_URL=https://188.com.vn
```

- Thay `https://api.188.com.vn` bằng URL backend thật của bạn (subdomain hoặc domain riêng).

Trên Vercel/Railway/Netlify: vào **Settings → Environment variables** và thêm các biến trên cho môi trường **Production**.

---

### Bước 3 – Chạy build frontend (trên máy bạn)

Trên máy của bạn (PowerShell hoặc CMD):

```bash
cd frontend
npm install
npm run build
```

- Nếu build **thành công** → bạn có thể deploy thư mục `.next` hoặc dùng lệnh `npm run start`.
- Nếu báo lỗi **EPERM / spawn**: thử chạy CMD/PowerShell **với quyền Administrator** hoặc tạm tắt phần mềm diệt virus đang chặn Node.

---

### Bước 4 – Chọn nơi chạy backend và frontend

Bạn cần **tự chọn** một trong các hướng sau (hoặc tương tự):

| Thành phần | Gợi ý | Việc bạn làm |
|------------|--------|-------------------------------|
| **Backend** | VPS (DigitalOcean, AWS EC2, Vultr…), Railway, Render | Thuê server, cài Python, chạy `uvicorn main:app --host 0.0.0.0 --port 8000` (không dùng `--reload`). |
| **Database** | Supabase, Neon, Railway PostgreSQL, hoặc PostgreSQL trên VPS | Tạo database, lấy chuỗi `DATABASE_URL` và ghi vào backend `.env`. |
| **Frontend** | Vercel, Netlify, hoặc cùng VPS với Nginx | Đẩy code frontend, set env (Bước 2), build và chạy (hoặc dùng “Build command” của Vercel/Netlify). |
| **Domain** | Mua domain (vd: 188.com.vn) | Trỏ domain/subdomain tới server hoặc Vercel/Netlify. |

Ví dụ nhanh:

- **Backend:** Trên VPS: `cd backend` → `pip install -r requirements.txt` → tạo `.env` → `uvicorn main:app --host 0.0.0.0 --port 8000`.
- **Frontend trên Vercel:** Đẩy repo lên GitHub → kết nối Vercel → thêm env `NEXT_PUBLIC_API_BASE_URL` và `NEXT_PUBLIC_DOMAIN` → Deploy.

---

### Bước 5 – Bật HTTPS và kiểm tra

- Backend và frontend nên chạy qua **HTTPS** (dùng Nginx/Caddy trên VPS hoặc HTTPS mặc định của Vercel/Netlify).
- Sau khi deploy: mở frontend trên trình duyệt, thử đăng nhập, xem sản phẩm, giỏ hàng, checkout. Nếu lỗi 401/404/CORS thì kiểm tra lại `BACKEND_CORS_ORIGINS` và `NEXT_PUBLIC_API_BASE_URL`.

---

## Phần 2: Những gì đã được làm sẵn trong code (bạn không cần làm)

- **Backend:** CORS, JWT, SECRET_KEY đọc từ .env; có thể tắt Swagger bằng `DISABLE_DOCS=true`.
- **Frontend:** Trang checkout không còn dùng Ant Design → build không còn lỗi `antd/lib`.
- **Bảo mật:** Đã kiểm tra và ghi trong `SECURITY_AUDIT.md`; bạn chỉ cần cấu hình .env đúng.

---

## Tóm tắt checklist của BẠN

1. [ ] Backend: tạo `.env` từ `.env.example`, điền **SECRET_KEY**, **BACKEND_CORS_ORIGINS**, **DATABASE_URL**, **ENVIRONMENT=production**, **DEBUG=False**.
2. [ ] Frontend: khi deploy production, set **NEXT_PUBLIC_API_BASE_URL** (và nếu cần **NEXT_PUBLIC_DOMAIN** / **NEXT_PUBLIC_SITE_URL**).
3. [ ] Trên máy bạn: `cd frontend` → `npm install` → `npm run build` (build phải thành công).
4. [ ] Thuê server/database, deploy backend và frontend, trỏ domain, bật HTTPS.
5. [ ] Test đăng nhập, giỏ hàng, checkout trên domain thật.

Làm xong các bước trên là bạn có thể deploy; phần còn lại (server, domain, mua hosting) chỉ bạn mới thực hiện được.

---

## Phần 3: Chuẩn bị riêng VPS (script + SQL mẫu)

Xem thư mục **`deploy/`** trong repo: **`deploy/README.md`**, script **`deploy/prepare-vps.sh`**, mẫu PostgreSQL **`deploy/postgres-init.sql.example`**. Tóm tắt cũng nằm trong **`DEPLOY_READINESS.md`** mục **6**.
