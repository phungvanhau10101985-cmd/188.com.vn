#!/usr/bin/env bash
# Kiểm tra endpoint thống kê vận hành EMS (404 = backend cũ hoặc chưa restart 188-api).
# Usage: bash deploy/verify-shipping-ops-api.sh
set -u

PORT="${API_INTERNAL_PORT:-8001}"
BASE="http://127.0.0.1:${PORT}"

echo "==> Shipping operations API (${BASE})"
echo "    health: $(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 "${BASE}/health" 2>/dev/null || echo 000)"

ok=1
for path in \
  "/api/v1/orders/admin/shipping/operations-stats" \
  "/api/v1/orders/admin/shipping/operations-stats/timeline" \
  "/api/v1/orders/admin/shipping/ems-records"
do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${BASE}${path}" 2>/dev/null || echo "000")
  echo "    ${code}  ${path}"
  case "${code}" in
    401|403) ok=0 ;;
    404) ok=1 ;;
  esac
done

if [[ "${ok}" -eq 0 ]]; then
  echo "OK: Endpoint co tren server (401/403 khi chua gui token la binh thuong)."
  exit 0
fi

echo ""
echo "LOI: 404 hoac API khong chay — thu:"
echo "  cd /var/www/188.com.vn && git pull origin main"
echo "  grep operations-stats backend/app/api/endpoints/orders.py | head"
echo "  pm2 restart 188-api && sleep 3"
echo "  bash deploy/verify-shipping-ops-api.sh"
exit 1
