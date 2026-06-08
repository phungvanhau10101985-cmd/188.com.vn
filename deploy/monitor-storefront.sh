#!/usr/bin/env bash
# Ghi log + (tuỳ chọn) cảnh báo khi storefront không healthy.
# API đã có self-heal ~20s trong process — script này để THEO DÕI / báo admin sớm.
#
# Cron gợi ý (mỗi 2 phút, không cần 5 phút):
#   */2 * * * * cd /var/www/188.com.vn && bash deploy/monitor-storefront.sh >> /var/log/188-storefront-monitor.log 2>&1
#
# UptimeRobot (khuyến nghị): GET https://188.com.vn/health/storefront — expect 200, interval 1 phút.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${API_INTERNAL_PORT:-8001}"
LOG="${STOREFRONT_MONITOR_LOG:-/var/log/188-storefront-monitor.log}"
URL="${STOREFRONT_HEALTH_URL:-http://127.0.0.1:${API_PORT}/health/storefront}"
PUBLIC_URL="${STOREFRONT_HEALTH_PUBLIC_URL:-https://188.com.vn/health/storefront}"

ts="$(date '+%Y-%m-%d %H:%M:%S')"
code="000"
body=""
if command -v curl >/dev/null 2>&1; then
  body=$(curl -sS --connect-timeout 3 --max-time 12 "$URL" 2>/dev/null || true)
  code=$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 12 "$URL" 2>/dev/null || echo "000")
fi

if [[ "${code}" == "200" ]]; then
  echo "${ts} OK ${URL}"
  exit 0
fi

echo "${ts} ALERT storefront code=${code} url=${URL} public=${PUBLIC_URL}" | tee -a "${LOG}"
if [[ -n "${body}" ]]; then
  echo "  body: ${body:0:400}" | tee -a "${LOG}"
fi

if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  CRON_SECRET=""
  if [[ -f "${ROOT}/backend/.env" ]]; then
    CRON_SECRET="$(grep -E '^CRON_SECRET=' "${ROOT}/backend/.env" | head -1 | cut -d= -f2- | tr -d '\r\"' )"
  fi
  if [[ -n "${CRON_SECRET}" ]] && command -v curl >/dev/null 2>&1; then
    curl -sS -X POST -H "Authorization: Bearer ${CRON_SECRET}" \
      --connect-timeout 3 --max-time 15 \
      "http://127.0.0.1:${API_PORT}/health/ops-alert" >/dev/null 2>&1 || true
  else
    (
      cd "${ROOT}/backend"
      PYTHONPATH=. .venv/bin/python scripts/send_ops_health_alert.py \
        storefront_down \
        "Storefront health check thất bại (HTTP ${code})" \
        "Monitor: ${URL} — khách có thể không load SP/menu."
    ) || true
  fi
fi

# Self-heal trong API thường đã xử lý — chỉ restart nếu vẫn fail sau 45s (2 lần probe self-heal)
if [[ "${MONITOR_RESTART_ON_FAIL:-0}" == "1" ]]; then
  echo "${ts} MONITOR_RESTART_ON_FAIL=1 → pm2 restart 188-api" | tee -a "${LOG}"
  pm2 restart "${PM2_API_NAME:-188-api}" --update-env 2>/dev/null || true
fi

exit 1
