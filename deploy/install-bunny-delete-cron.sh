#!/usr/bin/env bash
# Cài cron dọn Bunny CDN từ bảng pending_bunny_deletes (mỗi 5 phút).
#
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/install-bunny-delete-cron.sh
#
# Yêu cầu: CRON_SECRET trong backend/.env; API đã deploy endpoint
#   GET /api/v1/products/cron/process-pending-bunny-deletes
#
# Gọi localhost:8001 (không qua Cloudflare/nginx) — tránh 502 khi API vừa restart.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/backend/.env"
MARKER="products/cron/process-pending-bunny-deletes"
API_PORT="${API_INTERNAL_PORT:-8001}"
LOCAL_URL="http://127.0.0.1:${API_PORT}/api/v1/${MARKER}"
LOG="${BUNNY_DELETE_CRON_LOG:-/var/log/188-bunny-delete-cron.log}"
WAIT_HEALTH_SEC="${BUNNY_DELETE_WAIT_HEALTH_SEC:-90}"

echo "==> Cài cron dọn Bunny pending deletes (mỗi 5 phút)"
echo "    Project: ${ROOT}"
echo "    Probe:   ${LOCAL_URL}"
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

JOB="*/5 * * * * curl -sS -m 300 -H \"Authorization: Bearer ${CRON_SECRET}\" \"${LOCAL_URL}\" >> ${LOG} 2>&1"

touch "${LOG}" 2>/dev/null || sudo touch "${LOG}" 2>/dev/null || true
chmod 644 "${LOG}" 2>/dev/null || sudo chmod 644 "${LOG}" 2>/dev/null || true

existing="$(crontab -l 2>/dev/null || true)"
# Nâng cấp dòng cũ (https://domain/...) sang localhost nếu đã có marker
if grep -Fq "${MARKER}" <<<"${existing}"; then
  if grep -Fq "127.0.0.1:${API_PORT}/api/v1/${MARKER}" <<<"${existing}"; then
    echo "✓ crontab đã có process-pending-bunny-deletes (localhost) — bỏ qua thêm mới"
  else
    echo "==> Cập nhật cron cũ → gọi 127.0.0.1:${API_PORT} (tránh 502 qua Cloudflare)"
    updated="$(printf '%s\n' "${existing}" | grep -vF "${MARKER}" || true)"
    (printf '%s\n' "${updated}"; echo "${JOB}") | crontab -
    echo "✓ Đã thay dòng cron Bunny delete"
  fi
else
  (printf '%s\n' "${existing}"; echo "${JOB}") | crontab -
  echo "✓ Đã thêm cron:"
  echo "  */5 * * * * curl … ${LOCAL_URL}"
fi

echo ""
echo "==> crontab hiện tại (dòng Bunny delete):"
crontab -l 2>/dev/null | grep -F "${MARKER}" || echo "  (không thấy — kiểm tra crontab -l)"

echo ""
echo "==> Chờ API /health (tối đa ${WAIT_HEALTH_SEC}s)…"
health="000"
deadline=$((SECONDS + WAIT_HEALTH_SEC))
while (( SECONDS < deadline )); do
  health="$(curl -sS -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:${API_PORT}/health" 2>/dev/null || echo 000)"
  if [[ "${health}" == "200" ]]; then
    break
  fi
  sleep 2
done
echo "    GET /health → ${health}"

if [[ "${health}" != "200" ]]; then
  echo "⚠️ API chưa healthy sau ${WAIT_HEALTH_SEC}s — cron đã ghi crontab; thử lại khi API ổn:"
  echo "    bash deploy/install-bunny-delete-cron.sh"
  echo "    pm2 logs 188-api --lines 80 --nostream"
  exit 0
fi

echo ""
echo "==> Chạy thử một lần (localhost)…"
HTTP_CODE="$(curl -sS -o /tmp/188-bunny-delete-cron-try.json -w '%{http_code}' -m 120 \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  "${LOCAL_URL}" || true)"
echo "    HTTP ${HTTP_CODE}"
if [[ -f /tmp/188-bunny-delete-cron-try.json ]]; then
  head -c 500 /tmp/188-bunny-delete-cron-try.json; echo
fi
if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "⚠️ Endpoint chưa OK. Kiểm tra:"
  echo "    pm2 logs 188-api --lines 80 --nostream | tail -40"
  echo "    curl -sS -m 30 -H \"Authorization: Bearer \$CRON_SECRET\" ${LOCAL_URL}"
  exit 0
fi

echo ""
echo "✅ Xong. Log: tail -f ${LOG}"
