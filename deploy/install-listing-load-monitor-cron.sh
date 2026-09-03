#!/usr/bin/env bash
# Cài cron đo tải listing (mỗi 5 phút) — không restart PM2.
# Usage: cd /var/www/188.com.vn && bash deploy/install-listing-load-monitor-cron.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${LISTING_LOAD_LOG:-/var/log/188-listing-load.log}"
MARKER="deploy/monitor-listing-load.sh"
JOB="*/5 * * * * cd ${ROOT} && bash deploy/monitor-listing-load.sh"

if [[ ! -f "${ROOT}/deploy/monitor-listing-load.sh" ]]; then
  echo "❌ Không tìm thấy ${ROOT}/deploy/monitor-listing-load.sh"
  exit 1
fi

touch "${LOG}" 2>/dev/null || true
chmod 644 "${LOG}" 2>/dev/null || true

existing="$(crontab -l 2>/dev/null || true)"
if echo "${existing}" | grep -Fq "${MARKER}"; then
  echo "✓ crontab đã có monitor-listing-load — bỏ qua thêm mới"
else
  (echo "${existing}"; echo "${JOB}") | crontab -
  echo "✓ Đã thêm crontab:"
  echo "  ${JOB}"
fi

bash "${ROOT}/deploy/monitor-listing-load.sh"
echo "✓ Sample: tail -n 3 ${LOG}"
tail -n 3 "${LOG}" 2>/dev/null || true
