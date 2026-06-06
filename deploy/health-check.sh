#!/usr/bin/env bash
# Kiểm tra sức khỏe 188-api + 188-web (sau deploy hoặc debug).
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/health-check.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=health-lib.sh
source "${PROJECT_ROOT}/deploy/health-lib.sh"

API_PORT="${API_INTERNAL_PORT:-8001}"
WEB_PORT="${WEB_INTERNAL_PORT:-3001}"
WEB_PATH="${WEB_HEALTH_PATH:-/robots.txt}"
API_WAIT="${HEALTH_API_WAIT_SEC:-45}"
WEB_WAIT="${HEALTH_WEB_WAIT_SEC:-60}"

port_is_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -qE ":${port}\\b"
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "${port}" >/dev/null 2>&1
    return $?
  fi
  return 1
}

echo "==> Health check 188.com.vn (${PROJECT_ROOT})"
echo "    API : http://127.0.0.1:${API_PORT}/health"
echo "    Web : http://127.0.0.1:${WEB_PORT}${WEB_PATH}"

if pgrep -f 'image_localization_job|imgloc-|_multiprocess_job_entry' >/dev/null 2>&1; then
  echo "⚠️  Job bản địa hóa ảnh/OCR đang chạy — API có thể timeout."
  echo "    Chạy: bash deploy/cancel-image-localization-job.sh --all-active --nuke"
fi

api_code="000"
for _i in $(seq 1 "${API_WAIT}"); do
  if port_is_listening "${API_PORT}"; then
    api_code=$(health_curl_http_code "http://127.0.0.1:${API_PORT}/health" 3)
    [[ "${api_code}" == "200" ]] && break
  fi
  api_code="000"
  sleep 1
done

web_code="000"
for _i in $(seq 1 "${WEB_WAIT}"); do
  if port_is_listening "${WEB_PORT}"; then
    web_code=$(health_curl_http_code "http://127.0.0.1:${WEB_PORT}${WEB_PATH}" 5)
    [[ "${web_code}" == "200" || "${web_code}" == "204" ]] && break
  fi
  web_code="000"
  sleep 1
done

products_code="000"
sale_code="000"
homepage_code="000"
if [[ "${api_code}" == "200" ]]; then
  products_code=$(health_curl_products_probe "${API_PORT}")
  if [[ "${products_code}" != "200" ]]; then
    echo "    → products timeout — dọn pool DB (idle in transaction)…" >&2
    health_terminate_idle_db_transactions
    sleep 2
    products_code=$(health_curl_products_probe "${API_PORT}" 2 30)
  fi
  sale_code=$(health_curl_http_code "http://127.0.0.1:${API_PORT}/api/v1/sale-calendar/current" 15)
fi

if [[ "${web_code}" == "200" || "${web_code}" == "204" ]]; then
  homepage_code=$(health_curl_homepage_smoke "http://127.0.0.1:${WEB_PORT}")
fi

echo ""
echo "    GET /health                          → ${api_code}"
echo "    GET ${WEB_PATH}                      → ${web_code}"
echo "    GET /api/v1/products/?limit=${HEALTH_PRODUCTS_LIMIT:-8}&skip_total=true → ${products_code}"
echo "    GET /api/v1/sale-calendar/current    → ${sale_code}"
echo "    GET / (homepage SSR smoke)           → ${homepage_code}"
echo ""
echo "    pm2:"
pm2 list 2>/dev/null | grep -E '188-api|188-web|name' || pm2 list 2>/dev/null || true
echo ""
echo "    listen:"
ss -tlnp 2>/dev/null | grep -E ":(${API_PORT}|${WEB_PORT})\\b" || echo "    (chưa thấy cổng ${API_PORT}/${WEB_PORT})"

core_ok=0
[[ "${api_code}" == "200" && ( "${web_code}" == "200" || "${web_code}" == "204" ) && "${products_code}" == "200" ]] && core_ok=1

if [[ "${core_ok}" == "1" && "${homepage_code}" == "200" ]]; then
  echo ""
  echo "✅ Sức khỏe: OK (API + Web + products + homepage)."
  exit 0
fi

if [[ "${core_ok}" == "1" ]]; then
  echo ""
  echo "✅ Sức khỏe cốt lõi: OK (API + Web + products)."
  if [[ "${homepage_code}" != "200" ]]; then
    echo "⚠️  Homepage SSR chưa 200 trong ${HEALTH_HOMEPAGE_CURL_MAX_SEC:-120}s — xem pm2 logs 188-web"
    [[ "${DEPLOY_REQUIRE_HOMEPAGE:-0}" == "1" ]] && exit 1
  fi
  exit 0
fi

echo ""
echo "⚠️  Sức khỏe bất thường."
if [[ "${api_code}" == "200" && "${products_code}" != "200" ]]; then
  echo "    /health OK nhưng products timeout → pool DB kẹt hoặc job OCR ảnh chiếm API."
  echo "    Thử: bash deploy/relieve-db-after-restart.sh"
  echo "    Hoặc: bash deploy/cancel-image-localization-job.sh --all-active --nuke"
fi
echo "    API:  bash deploy/fix-api-health.sh"
echo "    Web:  bash deploy/fix-web-health.sh"
echo "    DB:   bash deploy/relieve-db-after-restart.sh"
exit 1
