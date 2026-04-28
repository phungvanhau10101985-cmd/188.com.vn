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

1. Trong thư mục **frontend**, tạo hoặc sửa file `**.env.local`** (hoặc cấu hình env trên nền tảng deploy).
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


| Thành phần   | Gợi ý                                                        | Việc bạn làm                                                                                         |
| ------------ | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| **Backend**  | VPS (DigitalOcean, AWS EC2, Vultr…), Railway, Render         | Thuê server, cài Python, chạy `uvicorn main:app --host 0.0.0.0 --port 8000` (không dùng `--reload`). |
| **Database** | Supabase, Neon, Railway PostgreSQL, hoặc PostgreSQL trên VPS | Tạo database, lấy chuỗi `DATABASE_URL` và ghi vào backend `.env`.                                    |
| **Frontend** | Vercel, Netlify, hoặc cùng VPS với Nginx                     | Đẩy code frontend, set env (Bước 2), build và chạy (hoặc dùng “Build command” của Vercel/Netlify).   |
| **Domain**   | Mua domain (vd: 188.com.vn)                                  | Trỏ domain/subdomain tới server hoặc Vercel/Netlify.                                                 |


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

Xem thư mục `**deploy/`** trong repo: `**deploy/README.md**`, script `**deploy/prepare-vps.sh**`, mẫu PostgreSQL `**deploy/postgres-init.sql.example**`. Tóm tắt cũng nằm trong `**DEPLOY_READINESS.md**` mục **6**.

---

## Phần 4: Lộ trình VPS (làm lần lượt, xong bước này mới sang bước sau khi có thể)

Làm **trước khi** đổi DNS Cloudflare trỏ về IP VPS (trừ bước SSL nếu bắt buộc domain trỏ đúng IP).

**Lưu ý riêng repo này:** project **không dùng Alembic**. Bảng và migration chạy qua `init_database_tables()` trong `backend/main.py` khi process Uvicorn khởi động (và logic trong `app/db/migrations.py`). Uvicorn **phải** chạy từ thư mục `**backend/`** với module `**main:app**` (không phải `app.main:app`).

**Tóm tắt một dòng:**

PostgreSQL → đưa code → `.env` → chạy Uvicorn (tự/init DB khi startup) → Next build → Next (`PORT`) → Nginx (`/api`→API, `/`→Next) → test bằng `curl` + Host → Certbot (sau DNS) → đổi DNS Cloudflare.

### 0. Chuẩn bị

- Ghi lại IP VPS, SSH vào: `ssh user@IP`.
- Quyết định port nội bộ: **không trùng** process đang chạy (`ss -tlnp` hoặc `pm2 list`).

#### Cùng VPS với **nanoai.vn** (nanoai đang dùng cổng **3000**)


| Dịch vụ                         | nanoai.vn (giữ nguyên)        | 188.com.vn (đặt cố định)                                                                |
| ------------------------------- | ----------------------------- | --------------------------------------------------------------------------------------- |
| Next.js (public qua Nginx)      | `**127.0.0.1:3000`**          | `**127.0.0.1:3001**`                                                                    |
| Backend FastAPI (nếu tách cổng) | thường `8000` hoặc port riêng | **tránh trùng** — nếu `8000` đã có API nanoai → dùng ví dụ `**127.0.0.1:8001`** cho 188 |


Quy tắc:

- **Không** chạy Next 188 với `PORT=3000` — sẽ đụng nanoai.
- Toàn bộ bước 4–7 bên dưới: thay `**8000` → cổng API 188 thực tế** (vd. `8001`) và `**3001`** giữ cho Next 188; **Nginx** cho domain `188.com.vn` chỉ `proxy_pass` tới các cổng đó (`/api/` → API 188, `/` → `3001`).
- PostgreSQL: vẫn **database USER + DB riêng** cho 188 (không dùng DB nanoai).

### 1. Hệ thống cơ bản

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx certbot python3-certbot-nginx
```

(Nếu chưa có) cài **Node.js LTS**, **Python 3 + venv**, **PostgreSQL** (server hoặc client nếu DB ở máy khác).

### 2. PostgreSQL — database riêng cho 188

```bash
sudo -u postgres psql
```

Trong psql: tạo USER + DATABASE riêng, cấp quyền; **không** dùng chung DB với dự án khác (trừ khi cố ý). Tham chiếu mẫu: `deploy/postgres-init.sql.example`.

### 3. Đưa code lên VPS

Tạo thư mục, ví dụ: `/var/www/188-api` (backend), `/var/www/188-web` (frontend), hoặc một thư mục monorepo rồi `cd` vào từng phần:

```bash
git clone https://github.com/phungvanhau10101985-cmd/188.com.vn.git
# hoặc rsync từ máy dev
```

### 4. Backend (FastAPI)

```bash
cd /đường/dẫn/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file `**.env**` production: `DATABASE_URL`, `SECRET_KEY`, `BACKEND_CORS_ORIGINS`, Firebase, v.v. (xem Phần 1 và `backend/.env.example`).

**Migration / tạo bảng:** không có lệnh `alembic`. Cách đơn giản: sau khi `.env` đúng và DB trống/được phép migrate, chỉ cần **khởi động Uvicorn** một lần — app sẽ gọi migration khi startup. Hoặc (tùy) chạy script init nếu bạn có gói trong `deploy/` (xem `deploy/README.md`).

Chạy thử (listen localhost) — ví dụ cổng **8000**; nếu **8000** đã là API nanoai thì đổi **8001**:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Kiểm tra: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs` (ứng với port bạn chọn — rồi Ctrl+C).

### 5. Chạy backend “nền” (systemd hoặc PM2)

Service **Uvicorn** luôn lắng nghe `**127.0.0.1`** + **cổng riêng của 188** (vd. `8001` khi nanoai chiếm `8000`), khởi động lại khi reboot (working directory là `backend/`).

### 6. Frontend (Next.js)

```bash
cd /đường/dẫn/frontend
npm ci
npm run build
```

`**.env.production**` (hoặc env trước khi `build`): `NEXT_PUBLIC_API_BASE_URL` trỏ API production. Khi Nginx gộp domain (API dưới cùng host), thường đặt:

```env
NEXT_PUBLIC_API_BASE_URL=https://188.com.vn/api/v1
```

(Sau khi có HTTPS; giai đoạn test bằng IP + Host có thể dùng URL tạm — quan trọng là **rebuild** sau khi đổi env.)

Chạy thử — **luôn dùng `3001` (hoặc cổng khác ≠ 3000)** để không đụng nanoai:

```bash
PORT=3001 npm start
```

Kiểm tra: `curl -I http://127.0.0.1:3001` (rồi Ctrl+C).

### 7. Chạy frontend “nền”

PM2 hoặc systemd: `**PORT=3001**` — **không dùng 3000**. `pm2 save` nếu dùng PM2.

### 8. Nginx — site 188 (chưa bắt buộc SSL)

Tạo **server block riêng** (file mới trong `sites-available`), không sửa file Nginx của nanoai: `server_name 188.com.vn www.188.com.vn`.

- `location /api/` → `proxy_pass` tới `**http://127.0.0.1:<cổng_API_188>`** (vd. `8001` nếu 188 dùng 8001).
- `location /` → `proxy_pass http://127.0.0.1:3001` (Next 188).

Hai site cùng IP: Nginx phân biệt theo `**server_name**`, mỗi site một **upstream** cổng nội bộ khác nhau.

```bash
sudo ln -s /etc/nginx/sites-available/188-com-vn /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 9. Kiểm tra bằng IP + header Host (chưa đổi DNS)

```bash
curl -I http://IP_VPS -H "Host: 188.com.vn"
```

Kỳ vọng **200** hoặc **301** từ Nginx; không **502** (nếu 502 → kiểm tra service và `proxy_pass`).

### 10. SSL (Let’s Encrypt)

Chỉ làm khi DNS đã trỏ về IP VPS (hoặc bạn test cục bộ bằng hosts file và chấp nhận hạn chế):

```bash
sudo certbot --nginx -d 188.com.vn -d www.188.com.vn
```

### 11. Cuối cùng — Cloudflare

Sửa bản ghi **A** (`188.com.vn`, `www`, `*` nếu cần, CDN nếu dùng) → **IP VPS**. **Giữ nguyên MX / TXT** email.

---

### Phụ lục: Đưa file cấu hình (.env) từ máy Windows lên VPS (**scp**)

Repo trên VPS giả định: **`/var/www/188.com.vn`**. Trên **máy Windows** (CMD / PowerShell), dùng đường dẫn tuyệt đối tới thư mục project.

**Bắt buộc có sẵn trên PC:** `backend\.env`, `frontend\.env.local` (và nếu build production bằng file riêng: `frontend\.env.production`).

Thay `G:\python-code\188-com-vn` nếu đường dẫn khác; thay IP nếu không phải VPS này:

```powershell
# Backend — Python / FastAPI
scp -P 22 "G:\python-code\188-com-vn\backend\.env" root@14.225.218.39:/var/www/188.com.vn/backend/.env

# Frontend — Next.js (dev / thường dùng)
scp -P 22 "G:\python-code\188-com-vn\frontend\.env.local" root@14.225.218.39:/var/www/188.com.vn/frontend/.env.local
```

Nếu có **`.env.production`** (chỉ dùng khi bạn chủ định tách env build production):

```powershell
scp -P 22 "G:\python-code\188-com-vn\frontend\.env.production" root@14.225.218.39:/var/www/188.com.vn/frontend/.env.production
```

**UpGit** (tùy — binary thường nằm cùng chỗ `upgit.config.toml`; có thể chỉ cần một file trên VPS):

```powershell
scp -P 22 "G:\python-code\188-com-vn\upgit.config.toml" root@14.225.218.39:/var/www/188.com.vn/upgit.config.toml
```

Sau khi copy, trên VPS (SSH):

```bash
chmod 600 /var/www/188.com.vn/backend/.env /var/www/188.com.vn/frontend/.env.local 2>/dev/null
```

**Sau khi sửa env frontend:** `cd /var/www/188.com.vn/frontend` → `npm run build` → khởi động lại PM2 / process Next. **Sau khi sửa `backend/.env`:** khởi động lại service Uvicorn.