#!/usr/bin/env bash
# Kiểm tra endpoint thống kê vận hành EMS.
# Usage: bash deploy/verify-shipping-ops-api.sh
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${API_INTERNAL_PORT:-8001}"
BASE="http://127.0.0.1:${PORT}"
ORDERS_PY="${ROOT}/backend/app/api/endpoints/orders.py"

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

echo "==> Git (thu muc: ${ROOT})"
if command -v git >/dev/null 2>&1 && [[ -d "${ROOT}/.git" ]]; then
  git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || true
  git -C "${ROOT}" rev-parse --short origin/main 2>/dev/null && \
    echo "    origin/main: $(git -C "${ROOT}" rev-parse --short origin/main 2>/dev/null)" || true
fi

echo "==> File orders.py co route shipping?"
if [[ -f "${ORDERS_PY}" ]] && grep -q 'operations-stats' "${ORDERS_PY}" 2>/dev/null; then
  echo "    OK: co operations-stats trong orders.py"
else
  echo "    LOI: KHONG co operations-stats — can: git fetch origin && git reset --hard origin/main"
fi

echo "==> Routes shipping trong process Python (cung .venv PM2)"
if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  "${ROOT}/backend/.venv/bin/python" -c "
from main import app
paths = sorted({getattr(r, 'path', '') for r in app.routes if getattr(r, 'path', None) and 'shipping' in getattr(r, 'path', '')})
print('    So route shipping:', len(paths))
for p in paths[:5]:
    print('   ', p)
if not paths:
    print('    LOI: 0 route shipping — code tren dia khong khoi tao duoc orders shipping')
" 2>/dev/null | sed 's/^/    /' || echo "    (khong import duoc main:app — xem pm2 logs 188-api)"
else
  echo "    (bo qua — khong co backend/.venv/bin/python)"
fi

echo "==> HTTP (${BASE})"
health=$(http_code "${BASE}/health")
echo "    health: ${health}"
admin_stats=$(http_code "${BASE}/api/v1/orders/admin/stats")
echo "    orders/admin/stats (khong token): ${admin_stats}"

if [[ "${health}" == "000" ]]; then
  echo ""
  echo "LOI: Khong ket noi port ${PORT}. Chay: bash deploy/fix-api-health.sh"
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
if [[ "${admin_stats}" == "401" || "${admin_stats}" == "403" ]]; then
  echo "LOI: orders admin chay nhung shipping 404 — file orders.py tren VPS lech hoac import shipping that bai."
  echo "  pm2 logs 188-api --lines 80 --nostream | tail -40"
else
  echo "LOI: orders admin cung 404 (${admin_stats}) — module orders chua load."
fi
echo ""
echo "Sua nhanh (mat thay doi local tren VPS neu co):"
echo "  cd ${ROOT}"
echo "  git fetch origin && git reset --hard origin/main"
echo "  pm2 delete 188-api 2>/dev/null; pm2 start deploy/ecosystem.config.cjs --only 188-api"
echo "  sleep 4 && bash deploy/verify-shipping-ops-api.sh"
exit 1
