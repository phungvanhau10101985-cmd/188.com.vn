# Hướng dẫn cài đặt – 188.com.vn (môi trường dev local)

Tài liệu này mô tả cách chạy **backend FastAPI** và **frontend Next.js** trên máy Windows/Linux/macOS. Cổng chuẩn của repo: **API `8001`**, **Next `3001`** (trùng `dev-clear-start.ps1`, `backend/app/core/config.py` mặc định `SERVER_PORT=8001`).

**Deploy production:** xem [HUONG_DAN_DEPLOY.md](./HUONG_DAN_DEPLOY.md), [deploy/README.md](./deploy/README.md).

---

## 1. Yêu cầu trước khi cài

| Thành phần | Ghi chú |
|------------|---------|
| **Python** | 3.11+ khuyến nghị (khớp `backend/requirements.txt`) |
| **Node.js** | 18.x hoặc 20.x LTS |
| **Git** | Clone repo |

Tùy chọn: **PostgreSQL** (production); dev có thể dùng **SQLite** nếu `DATABASE_URL` trong `backend/.env` trỏ `sqlite:///./app.db` — xem [backend/POSTGRESQL_SETUP.md](./backend/POSTGRESQL_SETUP.md).

---

## 2. Backend (`backend/`)

```bash
cd backend
python -m venv .venv
```

**Windows (CMD):**

```bat
.venv\Scripts\activate
pip install -r requirements.txt
```

**Linux/macOS:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Tạo file môi trường:

```bash
copy .env.example .env
```

*(Linux/macOS: `cp .env.example .env`)* — mở `.env`, điền tối thiểu `SECRET_KEY`, `DATABASE_URL` (và các key theo tính năng bạn bật).

Chạy API (cổng **8001**):

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

Kiểm tra: mở **http://127.0.0.1:8001/docs** hoặc `curl http://127.0.0.1:8001/health`.

### Import sản phẩm từ link 1688 / Hibox (Playwright)

Sau `pip install -r requirements.txt`:

```bash
python -m playwright install chromium
```

Trên Linux nếu thiếu thư viện hệ thống: `python -m playwright install --with-deps chromium`.

---

## 3. Frontend (`frontend/`)

```bash
cd frontend
npm install
```

Copy mẫu env (tùy chọn — dev thuần local có thể bỏ qua nếu không cần ngrok/domain):

```bash
copy .env.local.example .env.local
```

*(Linux/macOS: `cp .env.local.example .env.local`)*

Trong `.env.local`, với **dev chỉ localhost**:

- `API_INTERNAL_ORIGIN=http://127.0.0.1:8001`
- Có thể **không** set `NEXT_PUBLIC_API_BASE_URL` — code mặc định gọi `http://localhost:8001/api/v1` khi trang chạy HTTP.

Chạy Next (script ép cổng **3001**):

```bash
npm run dev
```

Mở **http://localhost:3001** — ví dụ admin sản phẩm: **http://localhost:3001/admin/products**.

---

## 4. Windows: một lần bấm — `dev-clear-start.bat`

Ở thư mục gốc repo:

```bat
dev-clear-start.bat
```

Hoặc không cần ngrok:

```bat
dev-clear-start.bat -NoNgrok
```

Script sẽ: giải phóng cổng **8001** và **3001**, xóa cache `.next` / `__pycache__`, mở cửa sổ **uvicorn** và **`npm run dev`**. Chi tiết: `dev-clear-start.ps1`.

---

## 5. Khớp cổng – tránh `ERR_CONNECTION_REFUSED` / Failed to fetch

| Dịch vụ | Cổng mặc định repo |
|---------|---------------------|
| FastAPI | **8001** |
| Next.js (dev) | **3001** |

Nếu bạn đổi `SERVER_PORT` / lệnh `uvicorn`, cập nhật đồng thời:

- `frontend/.env.local`: `API_INTERNAL_ORIGIN`, `NEXT_PUBLIC_API_BASE_URL` (nếu có)
- Rồi **restart** cả backend và `npm run dev` (biến `NEXT_PUBLIC_*` không hot-reload đầy đủ).

---

## 6. Tài liệu liên quan

| File | Nội dung |
|------|----------|
| [backend/.env.example](./backend/.env.example) | Mẫu biến backend |
| [frontend/.env.example](./frontend/.env.example) | Mẫu biến frontend |
| [frontend/.env.local.example](./frontend/.env.local.example) | Dev + ngrok |
| [IMPORT_LINK_SOURCES_GUIDE.md](./IMPORT_LINK_SOURCES_GUIDE.md) | Luồng import 1688/Hibox, debug API |
| [DANH_SACH_ENV_CAN_DIEN.md](./DANH_SACH_ENV_CAN_DIEN.md) | Danh sách env theo tính năng |
