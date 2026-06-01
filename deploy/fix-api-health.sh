#!/usr/bin/env bash
# Sửa nhanh 188-api không listen :8001 (health curl → 000)
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/fix-api-health.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
VENV="${BACKEND}/.venv"
PM2_API="${PM2_API_NAME:-188-api}"
PORT="${API_INTERNAL_PORT:-8001}"

echo "==> 188-api health fix (port ${PORT})"
echo "    Project: ${PROJECT_ROOT}"

if [[ ! -d "${BACKEND}" ]]; then
  echo "❌ Không thấy ${BACKEND}"
  exit 1
fi

if [[ ! -f "${BACKEND}/.env" ]]; then
  echo "❌ Thiếu backend/.env"
  exit 1
fi

# Đồng bộ SERVER_PORT trong .env
if grep -q '^SERVER_PORT=' "${BACKEND}/.env"; then
  sed -i "s/^SERVER_PORT=.*/SERVER_PORT=${PORT}/" "${BACKEND}/.env"
else
  echo "SERVER_PORT=${PORT}" >> "${BACKEND}/.env"
fi
if grep -q '^RUN_DB_INIT_ON_STARTUP=' "${BACKEND}/.env"; then
  sed -i 's/^RUN_DB_INIT_ON_STARTUP=.*/RUN_DB_INIT_ON_STARTUP=0/' "${BACKEND}/.env"
else
  echo "RUN_DB_INIT_ON_STARTUP=0" >> "${BACKEND}/.env"
fi
echo "✓ RUN_DB_INIT_ON_STARTUP=0 (tránh kẹt startup migration)"

if [[ ! -x "${VENV}/bin/python" ]]; then
  echo "❌ Thiếu ${VENV}/bin/python — chạy deploy/update-vps.sh trước"
  exit 1
fi

echo ""
echo "==> Test import main:app (không qua PM2)"
cd "${BACKEND}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
if ! python -c "from main import app; print('import OK, routes:', len(app.routes))"; then
  echo "❌ Import main thất bại — xem traceback phía trên"
  exit 1
fi
deactivate

echo ""
echo "==> PM2 hiện tại"
pm2 describe "${PM2_API}" 2>/dev/null | grep -E 'status|restarts|cwd|script path|script args|error' || echo "(chưa có ${PM2_API})"

echo ""
echo "==> Cổng đang listen"
ss -tlnp 2>/dev/null | grep -E ":(${PORT}|8000|8001)\\b" || echo "(chưa có uvicorn trên ${PORT}/8000/8001)"

echo ""
echo "==> Khởi động lại ${PM2_API} bằng ecosystem.config.cjs"
cd "${PROJECT_ROOT}"
pm2 delete "${PM2_API}" 2>/dev/null || true
pm2 start deploy/ecosystem.config.cjs --only "${PM2_API}"
pm2 save || true

echo ""
echo "==> Chờ API (tối đa 45s)..."
code="000"
for _i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 \
    "http://127.0.0.1:${PORT}/health" 2>/dev/null) || true
  code="${code:-000}"
  if [[ "${code}" == "200" ]]; then
    break
  fi
  sleep 1
done

echo "    GET http://127.0.0.1:${PORT}/health → ${code}"

if [[ "${code}" != "200" ]]; then
  echo ""
  echo "❌ Vẫn không healthy. Log lỗi:"
  pm2 logs "${PM2_API}" --lines 60 --nostream 2>/dev/null || true
  echo ""
  echo "Thử chạy tay (debug):"
  echo "  cd ${BACKEND} && source .venv/bin/activate"
  echo "  python -m uvicorn main:app --host 127.0.0.1 --port ${PORT}"
  exit 1
fi

curl -s "http://127.0.0.1:${PORT}/health" | head -c 200
echo ""
echo "✅ 188-api OK trên port ${PORT}"
