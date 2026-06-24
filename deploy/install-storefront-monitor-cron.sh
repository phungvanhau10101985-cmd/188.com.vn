#!/usr/bin/env bash
# Cài cron monitor storefront (mỗi 2 phút) — không cần crontab -e thủ công.
#
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/install-storefront-monitor-cron.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${STOREFRONT_MONITOR_LOG:-/var/log/188-storefront-monitor.log}"
MARKER="deploy/monitor-storefront.sh"
JOB="*/2 * * * * cd ${ROOT} && bash deploy/monitor-storefront.sh"

echo "==> Cài cron monitor storefront (mỗi 2 phút)"
echo "    Project: ${ROOT}"
echo "    Log:     ${LOG}"

if [[ ! -x "${ROOT}/deploy/monitor-storefront.sh" && ! -f "${ROOT}/deploy/monitor-storefront.sh" ]]; then
  echo "❌ Không tìm thấy ${ROOT}/deploy/monitor-storefront.sh"
  exit 1
fi

touch "${LOG}" 2>/dev/null || sudo touch "${LOG}" 2>/dev/null || true
chmod 644 "${LOG}" 2>/dev/null || sudo chmod 644 "${LOG}" 2>/dev/null || true

existing="$(crontab -l 2>/dev/null || true)"
if echo "${existing}" | grep -Fq "${MARKER}"; then
  echo "✓ crontab đã có dòng monitor-storefront — bỏ qua thêm mới"
else
  (echo "${existing}"; echo "${JOB}") | crontab -
  echo "✓ Đã thêm crontab:"
  echo "  ${JOB}"
fi

echo ""
echo "==> crontab hiện tại (dòng monitor):"
crontab -l 2>/dev/null | grep -F "${MARKER}" || echo "  (không thấy — kiểm tra crontab -l)"

echo ""
echo "==> Chạy thử một lần…"
bash "${ROOT}/deploy/monitor-storefront.sh" && echo "✓ Monitor OK" || echo "⚠️  Monitor báo lỗi — xem ${LOG}"

echo ""
echo "✅ Xong. Log: tail -f ${LOG}"
