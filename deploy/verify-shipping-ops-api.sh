#!/usr/bin/env bash
# Kiểm tra endpoint thống kê vận hành EMS (404 = backend cũ hoặc chưa restart 188-api).
# Usage: bash deploy/verify-shipping-ops-api.sh
set -euo pipefail

PORT="${API_INTERNAL_PORT:-8001}"
BASE="http://127.0.0.1:${PORT}"

check() {
  local path="$1"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${BASE}${path}" 2>/dev/null) || code="000"
  echo "  ${code}  ${path}"
  case "${code}" in
    401|403) return 0 ;;
    404) return 1 ;;
    *) return 2 ;;
  esac
}

echo "==> Shipping operations API (${BASE})"
ok=0
check "/api/v1/orders/admin/shipping/operations-stats" || ok=1
check "/api/v1/orders/admin/shipping/operations-stats/timeline" || ok=1
check "/api/v1/orders/admin/shipping/ems-records" || true

if [[ "${ok}" -eq 0 ]]; then
  echo "✅ Endpoint có trên server (401/403 khi chưa gửi token là bình thường)."
  exit 0
fi

echo ""
echo "❌ 404 — FastAPI chưa có route. Trên VPS:"
echo "   cd /var/www/188.com.vn && git pull origin main"
echo "   pm2 restart 188-api"
echo "   bash deploy/verify-shipping-ops-api.sh"
exit 1
