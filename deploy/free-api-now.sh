#!/usr/bin/env bash
# Giải phóng API kẹt do job OCR ảnh — không dùng Python ORM (tránh treo).
# Usage: cd /var/www/188.com.vn && bash deploy/free-api-now.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${POSTGRES_DB_NAME:-188comvn}"
API_PORT="${API_INTERNAL_PORT:-8001}"
PM2_API="${PM2_API_NAME:-188-api}"

echo "==> free-api-now: dừng OCR/job ảnh + khởi động lại API sạch"

echo "1/6 Dừng PM2 API…"
pm2 stop "${PM2_API}" 2>/dev/null || true
sleep 3

echo "2/6 Giết worker OCR còn sót…"
pkill -9 -f "imgloc-" 2>/dev/null || true
pkill -9 -f "_multiprocess_job_entry" 2>/dev/null || true
pkill -9 -f "image_localization_job" 2>/dev/null || true
pkill -9 -f "image_localization_service" 2>/dev/null || true
sleep 1

echo "3/6 .env an toàn (không resume job ảnh)…"
bash "${ROOT}/deploy/ensure-api-safe-env.sh" || true

echo "4/6 Hủy job ảnh + reset SP processing (SQL trực tiếp)…"
if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
  sudo -u postgres psql -P pager=off -d "${DB_NAME}" -v ON_ERROR_STOP=1 <<'SQL' || true
UPDATE image_localization_jobs
SET status = 'cancelled',
    phase = 'cancelled',
    cancel_requested = TRUE,
    current_product_id = NULL,
    message = 'Hủy cứng (deploy/free-api-now.sh)',
    finished_at = NOW(),
    updated_at = NOW()
WHERE status IN ('queued', 'running');

UPDATE products
SET image_localization_status = 'pending',
    image_localization_error = NULL
WHERE image_localization_status = 'processing';

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database()
  AND state = 'idle in transaction'
  AND pid <> pg_backend_pid();
SQL
else
  echo "    (bỏ qua psql — không có postgres/sudo)"
fi

echo "5/6 Khởi động lại API từ ecosystem (resume job ảnh = false)…"
pm2 delete "${PM2_API}" 2>/dev/null || true
cd "${ROOT}"
IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP=false RUN_DB_INIT_ON_STARTUP=0 \
  pm2 start deploy/ecosystem.config.cjs --only "${PM2_API}"
pm2 save 2>/dev/null || true

echo "6/6 Kiểm tra nhanh (tối đa 45s)…"
health="000"
for _i in $(seq 1 45); do
  health=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 \
    "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo "000")
  [[ "${health}" == "200" ]] && break
  sleep 1
done
echo "    GET /health → ${health}"

products="000"
if [[ "${health}" == "200" ]]; then
  products=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 25 \
    "http://127.0.0.1:${API_PORT}/api/v1/products/?limit=4&skip=0&is_active=true&skip_total=true" \
    2>/dev/null || echo "000")
  echo "    GET /api/v1/products/?limit=4 → ${products}"
fi

if [[ "${health}" == "200" && "${products}" == "200" ]]; then
  echo ""
  echo "✅ API đã sẵn sàng. Chạy: bash deploy/health-check.sh"
  exit 0
fi

echo ""
echo "⚠️  API chưa ổn — gửi output: pm2 logs ${PM2_API} --lines 40 --nostream"
exit 1
