#!/usr/bin/env bash
# Sau deploy/restart API: pool DB + dọn connection kẹt + tắt resume job ảnh OCR.
# Usage: cd /var/www/188.com.vn && bash deploy/relieve-db-after-restart.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=health-lib.sh
source "${PROJECT_ROOT}/deploy/health-lib.sh"
ENV_FILE="${PROJECT_ROOT}/backend/.env"
DB_NAME="${POSTGRES_DB_NAME:-188comvn}"
API_PORT="${API_INTERNAL_PORT:-8001}"
PM2_API="${PM2_API_NAME:-188-api}"

echo "==> relieve-db-after-restart (${DB_NAME})"

bash "${PROJECT_ROOT}/deploy/ensure-api-safe-env.sh" || true

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

imgloc_running=0
if pgrep -f 'image_localization_job|imgloc-|_multiprocess_job_entry' >/dev/null 2>&1; then
  imgloc_running=1
  echo "⚠️  Phát hiện tiến trình bản địa hóa ảnh/OCR — API storefront sẽ chậm/timeout."
fi

if [[ "${imgloc_running}" == "1" && "${RELIEVE_CANCEL_IMGLOC_JOBS:-1}" == "1" ]]; then
  echo "==> Hủy job ảnh đang chạy (free-api-now)…"
  bash "${PROJECT_ROOT}/deploy/free-api-now.sh" || true
else
  echo "==> PM2 restart ${PM2_API} (áp dụng pool + tắt resume job ảnh)…"
  pm2 restart "${PM2_API}" --update-env 2>/dev/null || \
    pm2 start "${PROJECT_ROOT}/deploy/ecosystem.config.cjs" --only "${PM2_API}"
  pm2 save 2>/dev/null || true
fi

echo "    Chờ API /health…"
api_code="000"
for _i in $(seq 1 45); do
  api_code=$(health_curl_http_code "http://127.0.0.1:${API_PORT}/health" 3)
  [[ "${api_code}" == "200" ]] && break
  sleep 1
done
echo "    GET /health → ${api_code}"

if command -v curl >/dev/null 2>&1; then
  code=$(health_curl_products_probe "${API_PORT}" 4 20)
  if [[ "${code}" != "200" ]]; then
    echo "    → products chưa 200 — dọn pool DB lần nữa…"
    health_terminate_idle_db_transactions
    sleep 2
    code=$(health_curl_products_probe "${API_PORT}" 2 25)
  fi
  echo "    GET /api/v1/products/ (storefront probe) → ${code}"
  if [[ "${code}" != "200" ]]; then
    echo "⚠️  Products API chưa 200 — chạy free-api-now…"
    bash "${PROJECT_ROOT}/deploy/free-api-now.sh" || true
    exit 1
  fi
fi

echo "✅ relieve-db OK"
