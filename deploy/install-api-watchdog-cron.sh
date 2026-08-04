#!/usr/bin/env bash
# Cài cron watchdog API (mỗi 2 phút), để khôi phục khi 188-api crash,
# không listen cổng hoặc PM2 bị kẹt ở "waiting restart".
#
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/install-api-watchdog-cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${API_WATCHDOG_LOG:-/var/log/188-watchdog.log}"
MARKER="deploy/watchdog-api.sh"
JOB="*/2 * * * * cd ${ROOT} && bash deploy/watchdog-api.sh >> ${LOG} 2>&1"

echo "==> Cài cron watchdog 188-api (mỗi 2 phút)"
echo "    Project: ${ROOT}"
echo "    Log:     ${LOG}"

if [[ ! -f "${ROOT}/deploy/watchdog-api.sh" ]]; then
  echo "❌ Không tìm thấy ${ROOT}/deploy/watchdog-api.sh"
  exit 1
fi

touch "${LOG}" 2>/dev/null || sudo touch "${LOG}" 2>/dev/null || true
chmod 644 "${LOG}" 2>/dev/null || sudo chmod 644 "${LOG}" 2>/dev/null || true

existing="$(crontab -l 2>/dev/null || true)"
if grep -Fq "${MARKER}" <<<"${existing}"; then
  echo "✓ crontab đã có watchdog-api — bỏ qua thêm mới"
else
  (printf '%s\n' "${existing}"; echo "${JOB}") | crontab -
  echo "✓ Đã thêm cron:"
  echo "  ${JOB}"
fi

echo ""
echo "==> crontab hiện tại (dòng watchdog):"
crontab -l 2>/dev/null | grep -F "${MARKER}" || echo "  (không thấy — kiểm tra crontab -l)"

echo ""
echo "==> Chạy thử một lần…"
bash "${ROOT}/deploy/watchdog-api.sh" && echo "✓ Watchdog OK" || echo "⚠️ Watchdog đã phát hiện/sửa lỗi — xem ${LOG}"

echo ""
echo "✅ Xong. Log: tail -f ${LOG}"
