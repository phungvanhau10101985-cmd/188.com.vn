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
INCIDENT_ROOT="${API_INCIDENT_DIR:-/var/log/188-api-incidents}"
INCIDENT_RETENTION_DAYS="${API_INCIDENT_RETENTION_DAYS:-14}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] watchdog"

capture_incident() {
  local reason="$1"
  local stamp incident_dir
  stamp="$(date '+%Y%m%d-%H%M%S')"
  incident_dir="${INCIDENT_ROOT}/${stamp}"

  mkdir -p "${incident_dir}"
  chmod 700 "${INCIDENT_ROOT}" "${incident_dir}" 2>/dev/null || true
  printf '%s\n' \
    "captured_at=$(date --iso-8601=seconds)" \
    "reason=${reason}" \
    "pm2_api=${PM2_API}" \
    "api_port=${API_PORT}" >"${incident_dir}/summary.txt"

  pm2 describe "${PM2_API}" >"${incident_dir}/pm2-describe.txt" 2>&1 || true
  pm2 jlist >"${incident_dir}/pm2-jlist.json" 2>&1 || true
  timeout 12 pm2 logs "${PM2_API}" --lines 300 --nostream >"${incident_dir}/pm2-output.log" 2>&1 || true
  timeout 12 pm2 logs "${PM2_API}" --err --lines 300 --nostream >"${incident_dir}/pm2-error.log" 2>&1 || true
  ps aux --sort=-%mem >"${incident_dir}/processes-by-memory.txt" 2>&1 || true
  ss -tlnp >"${incident_dir}/listening-ports.txt" 2>&1 || true
  dmesg -T >"${incident_dir}/kernel.log" 2>&1 || true
  if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    sudo -u postgres psql -P pager=off -d "${POSTGRES_DB_NAME:-188comvn}" \
      -c "SELECT pid, usename, state, wait_event_type, wait_event, now() - query_start AS query_age, left(query, 500) AS query FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY query_start NULLS LAST;" \
      >"${incident_dir}/postgres-activity.txt" 2>&1 || true
  fi
  find "${INCIDENT_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime "+${INCIDENT_RETENTION_DAYS}" -exec rm -rf {} + 2>/dev/null || true

  printf '%s\n' "${incident_dir}"
}

send_incident_alert() {
  local reason="$1"
  local incident_dir="$2"
  local detail="Watchdog phát hiện ${reason}. Snapshot điều tra: ${incident_dir}"

  if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
    (
      cd "${ROOT}/backend"
      PYTHONPATH=. .venv/bin/python scripts/send_ops_health_alert.py \
        api_watchdog_restart \
        "Watchdog phục hồi 188-api" \
        "${detail}"
    ) || echo "${LOG_PREFIX} không gửi được email cảnh báo (xem OPS_HEALTH_ALERT_EMAILS/SMTP)"
  fi
}

recover_api() {
  local reason="$1"
  local incident_dir
  incident_dir="$(capture_incident "${reason}")"
  echo "${LOG_PREFIX} ${reason} → incident=${incident_dir} → free-api-now"
  send_incident_alert "${reason}" "${incident_dir}"
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
