#!/usr/bin/env bash
# Một lần sau git pull — cấu hình chống treo storefront lâu dài (pool + OOS + monitor).
#
# Usage:
#   cd /var/www/188.com.vn && bash deploy/ensure-storefront-resilience.sh
#   bash deploy/free-api-now.sh   # nếu API đang kẹt ngay lúc chạy
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "==> Storefront resilience — pool, OOS, PM2 env"

bash "${ROOT}/deploy/apply-db-pool.sh"
bash "${ROOT}/deploy/ensure-api-safe-env.sh"

echo
echo "==> PM2: nạp ecosystem (env LEGACY_OOS=off, pool timeout 8s, self-heal 15s)"
pm2 delete 188-api 188-web 2>/dev/null || true
pm2 start deploy/ecosystem.config.cjs
pm2 save

echo
echo "==> Warm + health"
bash "${ROOT}/deploy/relieve-db-after-restart.sh" || true
sleep 2
bash "${ROOT}/deploy/health-check.sh" || true

echo
echo "==> Cron monitor storefront (mỗi 2 phút)"
bash "${ROOT}/deploy/install-storefront-monitor-cron.sh" || true
echo
echo "✓ Xong. UptimeRobot: GET https://188.com.vn/health/storefront mỗi 1 phút."
