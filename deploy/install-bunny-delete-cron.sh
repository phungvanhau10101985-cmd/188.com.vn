#!/usr/bin/env bash
# Cài cron dọn Bunny CDN từ bảng pending_bunny_deletes (mỗi 5 phút).
#
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/install-bunny-delete-cron.sh
#
# Yêu cầu: CRON_SECRET trong backend/.env; API đã deploy endpoint
#   GET /api/v1/products/cron/process-pending-bunny-deletes
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"
MARKER="products/cron/process-pending-bunny-deletes"
API_HOST="${API_HOST:-188.com.vn}"
LOG="${BUNNY_DELETE_CRON_LOG:-/var/log/188-bunny-delete-cron.log}"

echo "==> Cài cron dọn Bunny pending deletes (mỗi 5 phút)"
echo "    Project: ${ROOT}"
echo "    Host:    ${API_HOST}"
echo "    Log:     ${LOG}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ Không tìm thấy ${ENV_FILE}"
  exit 1
fi

CRON_SECRET="$(grep -E '^CRON_SECRET=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r\"' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
if [[ -z "${CRON_SECRET}" ]]; then
  echo "❌ CRON_SECRET trống trong ${ENV_FILE} — cấu hình rồi chạy lại."
  exit 1
fi

JOB="*/5 * * * * curl -sS -m 300 -H \"Authorization: Bearer ${CRON_SECRET}\" \"https://${API_HOST}/api/v1/${MARKER}\" >> ${LOG} 2>&1"

touch "${LOG}" 2>/dev/null || sudo touch "${LOG}" 2>/dev/null || true
chmod 644 "${LOG}" 2>/dev/null || sudo chmod 644 "${LOG}" 2>/dev/null || true

existing="$(crontab -l 2>/dev/null || true)"
if grep -Fq "${MARKER}" <<<"${existing}"; then
  echo "✓ crontab đã có process-pending-bunny-deletes — bỏ qua thêm mới"
else
  (printf '%s\n' "${existing}"; echo "${JOB}") | crontab -
  echo "✓ Đã thêm cron:"
  echo "  */5 * * * * curl … /api/v1/${MARKER}"
fi

echo ""
echo "==> crontab hiện tại (dòng Bunny delete):"
crontab -l 2>/dev/null | grep -F "${MARKER}" || echo "  (không thấy — kiểm tra crontab -l)"

echo ""
echo "==> Chạy thử một lần…"
HTTP_CODE="$(curl -sS -o /tmp/188-bunny-delete-cron-try.json -w '%{http_code}' -m 120 \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  "https://${API_HOST}/api/v1/${MARKER}" || true)"
echo "    HTTP ${HTTP_CODE}"
if [[ -f /tmp/188-bunny-delete-cron-try.json ]]; then
  head -c 500 /tmp/188-bunny-delete-cron-try.json; echo
fi
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "⚠️ Endpoint chưa OK (cần deploy backend + restart 188-api). Cron vẫn đã ghi vào crontab."
  exit 0
fi

echo ""
echo "✅ Xong. Log: tail -f ${LOG}"
