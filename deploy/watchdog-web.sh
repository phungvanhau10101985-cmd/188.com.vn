#!/usr/bin/env bash
# Đảm bảo frontend 188 + nanoai (thu-do-online) luôn listen.
# Tránh 502 Cloudflare khi OOM/watchdog API restart chỉ cứu 188-api rồi `pm2 save`
# làm mất 188-web / thu-do-online khỏi dump.
#
# Cron gợi ý (mỗi 2 phút):
#   */2 * * * * cd /var/www/188.com.vn && bash deploy/watchdog-web.sh >> /var/log/188-watchdog-web.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')] watchdog-web"
DEPLOY_LOCK="${ROOT}/deploy/.deploy-in-progress"

PM2_WEB="${PM2_WEB_NAME:-188-web}"
WEB_PORT="${WEB_INTERNAL_PORT:-3001}"
NANOAI_NAME="${NANOAI_PM2_NAME:-thu-do-online}"
NANOAI_DIR="${NANOAI_APP_DIR:-/var/www/Thu-do-online}"
NANOAI_PORT="${NANOAI_INTERNAL_PORT:-3000}"

if [[ -f "${DEPLOY_LOCK}" ]]; then
  lock_mtime=$(stat -c %Y "${DEPLOY_LOCK}" 2>/dev/null || echo 0)
  now=$(date +%s)
  lock_age=$((now - lock_mtime))
  if [[ "${lock_age}" -lt 7200 ]]; then
    echo "${LOG_PREFIX} skip — deploy đang chạy (lock ${lock_age}s)"
    exit 0
  fi
fi

port_ok() {
  local port="$1"
  ss -tln 2>/dev/null | grep -qE ":${port}\\s" || return 1
  return 0
}

http_ok() {
  local url="$1"
  local code
  code=$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 8 "${url}" 2>/dev/null || echo "000")
  [[ "${code}" == "200" || "${code}" == "301" || "${code}" == "302" || "${code}" == "307" || "${code}" == "308" ]]
}

# Cổng còn listen = process sống. Không restart chỉ vì HTTP chậm
# (trang chủ Next / shop HTML > 8s → SIGKILL → 502). Chỉ cứu khi mất cổng.
ensure_app() {
  local name="$1"
  local port="$2"
  local health_url="$3"
  local ecosystem="$4"
  local only="$5"

  if port_ok "${port}"; then
    if http_ok "${health_url}"; then
      echo "${LOG_PREFIX} OK ${name} :${port}"
    else
      echo "${LOG_PREFIX} SLOW ${name} :${port} — cổng còn listen, không restart"
    fi
    return 0
  fi

  echo "${LOG_PREFIX} RECOVER ${name} (port down) → pm2 start ${ecosystem} --only ${only}"
  if pm2 describe "${name}" &>/dev/null; then
    pm2 restart "${name}" --update-env 2>/dev/null || pm2 start "${name}" --update-env 2>/dev/null || true
  else
    pm2 start "${ecosystem}" --only "${only}" 2>/dev/null || true
  fi

  local i
  for i in $(seq 1 30); do
    if port_ok "${port}"; then
      echo "${LOG_PREFIX} recovered ${name}"
      return 0
    fi
    sleep 1
  done
  echo "${LOG_PREFIX} FAIL ${name} vẫn chưa listen sau recover"
  return 1
}

ok=0
ensure_app \
  "${PM2_WEB}" \
  "${WEB_PORT}" \
  "http://127.0.0.1:${WEB_PORT}/robots.txt" \
  "${ROOT}/deploy/ecosystem.config.cjs" \
  "${PM2_WEB}" && ok=$((ok + 1)) || true

if [[ -f "${NANOAI_DIR}/ecosystem.config.cjs" ]]; then
  ensure_app \
    "${NANOAI_NAME}" \
    "${NANOAI_PORT}" \
    "http://127.0.0.1:${NANOAI_PORT}/api/health" \
    "${NANOAI_DIR}/ecosystem.config.cjs" \
    "${NANOAI_NAME}" && ok=$((ok + 1)) || true
else
  echo "${LOG_PREFIX} skip nanoai — không thấy ${NANOAI_DIR}/ecosystem.config.cjs"
fi

# Chỉ save khi cả hai cổng chính đang listen — tránh dump thiếu app.
if port_ok "${WEB_PORT}" && port_ok "${NANOAI_PORT}"; then
  pm2 save 2>/dev/null || true
  echo "${LOG_PREFIX} pm2 save (web+nanoai listen OK)"
else
  echo "${LOG_PREFIX} skip pm2 save — còn app thiếu (web=$(port_ok ${WEB_PORT} && echo up || echo down) nanoai=$(port_ok ${NANOAI_PORT} && echo up || echo down))"
fi
