#!/usr/bin/env bash
# Watchdog ngoài process cho API. Chạy mỗi 2 phút từ cron để kéo API dậy
# ngay cả khi pool self-heal trong process không còn chạy (crash/PM2 waiting restart).
#
# Usage:
#   */2 * * * * cd /var/www/188.com.vn && bash deploy/watchdog-api.sh >> /var/log/188-watchdog.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=health-lib.sh
source "${ROOT}/deploy/health-lib.sh"

API_PORT="${API_INTERNAL_PORT:-8001}"
PM2_API="${PM2_API_NAME:-188-api}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] watchdog"

recover_api() {
  local reason="$1"
  echo "${LOG_PREFIX} ${reason} → free-api-now"
  bash "${ROOT}/deploy/free-api-now.sh"
}

pm2_state="$(
  pm2 jlist 2>/dev/null |
    node -e '
      let raw = "";
      process.stdin.setEncoding("utf8");
      process.stdin.on("data", (chunk) => { raw += chunk; });
      process.stdin.on("end", () => {
        try {
          const apps = JSON.parse(raw);
          const app = apps.find((item) => item.name === process.argv[1]);
          process.stdout.write(app?.pm2_env?.status || "missing");
        } catch {
          process.stdout.write("unavailable");
        }
      });
    ' "${PM2_API}" 2>/dev/null || true
)"

if [[ "${pm2_state}" != "online" ]]; then
  recover_api "PM2 ${PM2_API} status=${pm2_state:-unavailable}"
  exit 0
fi

health=$(health_curl_http_code "http://127.0.0.1:${API_PORT}/health" 5)
if [[ "${health}" != "200" ]]; then
  recover_api "/health=${health}"
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
  recover_api "products vẫn ${products}"
  exit 0
fi

if pgrep -f 'image_localization_job|imgloc-|_multiprocess_job_entry' >/dev/null 2>&1; then
  recover_api "OCR worker đang chạy"
  exit 0
fi

echo "${LOG_PREFIX} OK (pm2=online health=200 products=200)"
