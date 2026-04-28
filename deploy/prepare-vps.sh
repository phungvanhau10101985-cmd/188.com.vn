#!/usr/bin/env bash
# Chuẩn bị môi trường VPS (Ubuntu/Debian) — Python venv, dependencies, khởi tạo schema DB.
# Usage: từ root repo:  bash deploy/prepare-vps.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
FRONTEND="${PROJECT_ROOT}/frontend"
VENV="${BACKEND}/.venv"

echo "==> Root dự án: ${PROJECT_ROOT}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Cài Python 3 + venv:"
  echo "  sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip build-essential"
  exit 1
fi

echo "==> Virtualenv: ${VENV}"
python3 -m venv "${VENV}"
# shellcheck disable=SC1090
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
pip install -r "${BACKEND}/requirements.txt"

echo "==> Khởi tạo bảng DB (cần backend/.env với DATABASE_URL đúng)"
cd "${BACKEND}"
set +e
python -c "from main import init_database_tables; init_database_tables()"
DB_INIT=$?
set -e
if [[ "$DB_INIT" -ne 0 ]]; then
  echo "⚠️  init_database_tables thất bại — kiểm tra PostgreSQL, DATABASE_URL trong backend/.env"
else
  echo "✅ Database schema / migration đã chạy."
fi

deactivate

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  echo "==> Build frontend (cần frontend/.env.local production)"
  cd "${FRONTEND}"
  if [[ -f .env.local ]] || [[ -f .env.production ]]; then
    npm ci
    npm run build
    echo "✅ npm run build xong."
  else
    echo "⚠️  Tạo frontend/.env.local (NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_CDN_URL, …) rồi chạy lại npm run build."
  fi
else
  echo "⚠️  Chưa có Node.js — cài Node 20 LTS rồi: cd frontend && npm ci && npm run build"
fi

echo ""
echo "==> Chạy API production (ví dụ, sau Nginx terminate SSL):"
echo "  cd ${BACKEND} && source .venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8000"
echo "==> Next.js: cd ${FRONTEND} && npm run start  (hoặc pm2)"
echo "Xem thêm: deploy/README.md, HUONG_DAN_DEPLOY.md"
