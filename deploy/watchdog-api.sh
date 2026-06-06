#!/usr/bin/env bash
# Cron watchdog: phát hiện API storefront timeout và tự phục hồi.
# Usage (VPS, mỗi 5 phút):
#   */5 * * * * cd /var/www/188.com.vn && bash deploy/watchdog-api.sh >> /var/log/188-watchdog.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=health-lib.sh
source "${ROOT}/deploy/health-lib.sh"

API_PORT="${API_INTERNAL_PORT:-8001}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] watchdog"

health=$(health_curl_http_code "http://127.0.0.1:${API_PORT}/health" 5)
if [[ "${health}" != "200" ]]; then
  echo "${LOG_PREFIX} /health=${health} → free-api-now"
  bash "${ROOT}/deploy/free-api-now.sh"
  exit 0
fi

products=$(health_curl_products_probe "${API_PORT}" 2 20)
if [[ "${products}" != "200" ]]; then
  echo "${LOG_PREFIX} products=${products} → terminate idle + retry"
  health_terminate_idle_db_transactions
  sleep 2
  products=$(health_curl_products_probe "${API_PORT}" 2 25)
fi

if [[ "${products}" != "200" ]]; then
  echo "${LOG_PREFIX} products vẫn ${products} → free-api-now"
  bash "${ROOT}/deploy/free-api-now.sh"
  exit 0
fi

if pgrep -f 'image_localization_job|imgloc-|_multiprocess_job_entry' >/dev/null 2>&1; then
  echo "${LOG_PREFIX} OCR worker đang chạy → free-api-now"
  bash "${ROOT}/deploy/free-api-now.sh"
  exit 0
fi

echo "${LOG_PREFIX} OK (health=200 products=200)"
