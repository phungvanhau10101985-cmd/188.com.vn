#!/usr/bin/env bash
# Tạo PostgreSQL database khớp DATABASE_URL mặc định (188comvn).
# Chạy trên VPS một lần (user có quyền sudo -u postgres):
#   chmod +x deploy/postgres-create-db.sh && sudo bash deploy/postgres-create-db.sh
#
# Đổi tên DB:  POSTGRES_DB_NAME=mydb sudo -E bash deploy/postgres-create-db.sh
set -euo pipefail

DB_NAME="${POSTGRES_DB_NAME:-188comvn}"

exists() {
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1
}

if exists; then
  echo "==> Database '${DB_NAME}' đã tồn tại — không tạo lại."
  exit 0
fi

echo "==> Tạo database '${DB_NAME}' (UTF8, template0)…"
# Nếu báo lỗi locale, dùng tay: sudo -u postgres createdb ${DB_NAME}
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
CREATE DATABASE "${DB_NAME}" ENCODING 'UTF8' TEMPLATE template0;
SQL

echo "✅ Đã tạo xong. Kiểm tra: sudo -u postgres psql -lqt | cut -d \\| -f 1 | grep -w ${DB_NAME}"
echo "   Sau đó: cd backend && source .venv/bin/activate && python -c \"from main import init_database_tables; init_database_tables()\""
echo "   và: pm2 restart 188-api"
