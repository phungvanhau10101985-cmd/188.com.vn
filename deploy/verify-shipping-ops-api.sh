#!/usr/bin/env bash
# Kiểm tra endpoint thống kê vận hành EMS.
# Usage: bash deploy/verify-shipping-ops-api.sh
set -u

PORT="${API_INTERNAL_PORT:-8001}"
BASE="http://127.0.0.1:${PORT}"

http_code() {
  local url="$1"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${url}" 2>/dev/null) || true
  if [[ -z "${code}" ]]; then
    echo "000"
  else
    echo "${code}"
  fi
}

echo "==> Shipping operations API (${BASE})"

health=$(http_code "${BASE}/health")
echo "    health: ${health}"

if [[ "${health}" == "000" ]]; then
  echo ""
  echo "LOI: Khong ket noi duoc FastAPI tren port ${PORT} (PM2 co the 'online' nhung khong listen)."
  echo "  ss -tlnp | grep -E ':(${PORT})\\b'"
  echo "  pm2 show 188-api"
  echo "  pm2 logs 188-api --lines 40 --nostream"
  echo "  bash deploy/fix-api-health.sh"
  exit 1
fi

ok=1
for path in \
  "/api/v1/orders/admin/shipping/operations-stats" \
  "/api/v1/orders/admin/shipping/operations-stats/timeline" \
  "/api/v1/orders/admin/shipping/ems-records"
do
  code=$(http_code "${BASE}${path}")
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
echo "LOI: 404 — route chua co trong code dang chay. Thu:"
echo "  grep operations-stats backend/app/api/endpoints/orders.py | head"
echo "  git pull origin main && pm2 restart 188-api"
exit 1
