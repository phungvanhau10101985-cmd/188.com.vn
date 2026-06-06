#!/usr/bin/env bash
# Tuning VPS chia sẻ: .env pool + cache TTL + index Postgres + swap 4G.
# Gọi tự động từ deploy/update-vps.sh hoặc tay:
#   bash deploy/tune-db-vps.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

QUIET="${DEPLOY_TUNING_QUIET:-0}"

echo "==> [tuning] 1/4 Pool + cache TTL trong backend/.env"
if [[ -f "${ROOT}/backend/.env" ]]; then
  bash "${ROOT}/deploy/apply-db-pool.sh"
else
  echo "    (bỏ qua — chưa có backend/.env)"
fi

bash "${ROOT}/deploy/ensure-api-safe-env.sh" 2>/dev/null || true

echo
echo "==> [tuning] 2/4 Index ix_products_active_category_id"
if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  (
    cd "${ROOT}/backend"
    PYTHONPATH=. .venv/bin/python -c "
from app.db.migrations import migration_manager
ok = migration_manager.migrate_product_category_active_index()
print('    migrate_product_category_active_index:', ok)
" || echo "    (bỏ qua — DB chưa sẵn; index tạo khi API migrate lần sau)"
  )
else
  echo "    Chưa có backend/.venv — bỏ qua (sau pip install trong update-vps)"
fi

echo
echo "==> [tuning] 3/4 Postgres connections (nếu local)"
if command -v psql >/dev/null 2>&1 && sudo -u postgres psql -tAc "SELECT 1" >/dev/null 2>&1; then
  sudo -u postgres psql -tAc \
    "SELECT 'max_connections=' || setting FROM pg_settings WHERE name = 'max_connections';" \
    2>/dev/null || true
  sudo -u postgres psql -tAc \
    "SELECT datname || ': ' || count(*) FROM pg_stat_activity GROUP BY datname ORDER BY count DESC;" \
    2>/dev/null || true
else
  echo "    (bỏ qua — không postgres local / không sudo)"
fi

echo
echo "==> [tuning] 4/4 Swap 4G (nếu chưa có)"
if [[ "${DEPLOY_SKIP_SWAP:-0}" == "1" ]]; then
  echo "    DEPLOY_SKIP_SWAP=1 — bỏ qua."
elif swapon --show 2>/dev/null | grep -q .; then
  swapon --show
else
  SWAP_SCRIPT="${ROOT}/deploy/setup-swap.sh"
  if [[ -f "${SWAP_SCRIPT}" ]]; then
    if [[ "$(id -u)" -eq 0 ]]; then
      bash "${SWAP_SCRIPT}" || echo "    ⚠️  setup-swap thất bại — tiếp tục deploy"
    elif command -v sudo >/dev/null 2>&1; then
      sudo bash "${SWAP_SCRIPT}" || echo "    ⚠️  setup-swap thất bại — tiếp tục deploy"
    else
      echo "    (bỏ qua swap — cần root hoặc sudo)"
    fi
  fi
fi

if [[ "${QUIET}" != "1" ]]; then
  echo
  echo "✓ tune-db-vps xong. Tiếp: pm2 restart 188-api --update-env && pm2 save"
fi
