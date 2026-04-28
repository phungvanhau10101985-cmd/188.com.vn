# Hướng dẫn dùng PostgreSQL

## 0. Cài đặt driver (đã có trong requirements.txt)

```bash
pip install psycopg2-binary
# hoặc: pip install -r requirements.txt
```

## 1. Cài đặt PostgreSQL

**Windows:** Tải từ https://www.postgresql.org/download/windows/

**Ubuntu:** `sudo apt install postgresql postgresql-contrib`

**Docker:** `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=password -e POSTGRES_DB=188comvn postgres:15`

## 2. Tạo database

```sql
CREATE DATABASE 188comvn;
-- Hoặc: CREATE USER myuser WITH PASSWORD 'mypass'; CREATE DATABASE 188comvn OWNER myuser;
```

## 3. Cấu hình .env

Sao chép `.env.example` thành `.env` và cập nhật:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/188comvn
```

**Cloud (Supabase, Neon, Railway...):** Dán connection string vào `DATABASE_URL`.

## 4. Khởi tạo bảng

```bash
cd backend
python -m scripts.init_postgresql
```

Hoặc khởi động server – bảng sẽ tự tạo khi chạy lần đầu.

## 5. Migrate dữ liệu từ SQLite (tùy chọn)

Nếu đã có dữ liệu trong SQLite:

```bash
cd backend
# Đặt đường dẫn SQLite nguồn
$env:SQLITE_SOURCE="sqlite:///./app.db"   # PowerShell
# hoặc export SQLITE_SOURCE=sqlite:///./app.db  # Linux/Mac

python -m scripts.migrate_sqlite_to_postgres
```

## 6. Chạy server

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

---

**Quay lại SQLite (dev):** Đặt `DATABASE_URL=sqlite:///./app.db` trong `.env`.
