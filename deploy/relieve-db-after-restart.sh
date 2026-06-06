#!/usr/bin/env bash
# Sau deploy/restart API: pool DB + dọn connection kẹt — tránh /products timeout ngay sau pm2 restart.
# Usage: cd /var/www/188.com.vn && bash deploy/relieve-db-after-restart.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/backend/.env"
DB_NAME="${POSTGRES_DB_NAME:-188comvn}"

echo "==> relieve-db-after-restart (${DB_NAME})"

if [[ -f "${ENV_FILE}" ]]; then
  bash "${PROJECT_ROOT}/deploy/apply-db-pool.sh"
else
  echo "    (bỏ qua apply-db-pool — chưa có backend/.env)"
fi

if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
  sudo -u postgres psql -P pager=off -d "${DB_NAME}" -c \
    "ALTER DATABASE \"${DB_NAME}\" SET idle_in_transaction_session_timeout = '120s';" \
    2>/dev/null || true

  terminated=$(sudo -u postgres psql -P pager=off -d "${DB_NAME}" -tAc \
    "SELECT count(*) FROM (
       SELECT pg_terminate_backend(pid)
       FROM pg_stat_activity
       WHERE datname='${DB_NAME}' AND state='idle in transaction' AND pid <> pg_backend_pid()
     ) t;" \
    2>/dev/null || echo "0")
  echo "    Đã terminate idle-in-transaction: ${terminated:-0} connection"
else
  echo "    (bỏ qua PostgreSQL — không có user postgres / sudo)"
fi

API_PORT="${API_INTERNAL_PORT:-8001}"
if command -v curl >/dev/null 2>&1; then
  code="000"
  for _i in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 20 \
      "http://127.0.0.1:${API_PORT}/api/v1/products/?limit=48&skip=0&is_active=true" 2>/dev/null) || true
    [[ "${code}" == "200" ]] && break
    sleep 1
  done
  echo "    GET /api/v1/products/ (storefront) → ${code}"
  if [[ "${code}" != "200" ]]; then
    echo "⚠️  Products API chưa 200 — thử: pm2 restart 188-api --update-env"
    exit 1
  fi
fi

echo "✅ relieve-db OK"
