#!/usr/bin/env bash
# Kiểm tra endpoint admin VPS backup sau deploy.
# Usage: bash deploy/verify-vps-backup-api.sh
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
PORT="${API_INTERNAL_PORT:-8001}"
BASE="http://127.0.0.1:${PORT}"
MAIN_PY="${BACKEND}/main.py"
VPS_BACKUP_PY="${BACKEND}/app/api/endpoints/vps_backup_admin.py"

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

echo "==> File vps_backup_admin.py tren dia?"
if [[ -f "${VPS_BACKUP_PY}" ]]; then
  echo "    OK: co ${VPS_BACKUP_PY}"
else
  echo "    LOI: thieu vps_backup_admin.py — can: git fetch origin && git reset --hard origin/main"
fi

echo "==> main.py co load vps_backup_admin?"
if [[ -f "${MAIN_PY}" ]] && grep -q 'vps_backup_admin' "${MAIN_PY}" 2>/dev/null; then
  echo "    OK: main.py routes_config co vps_backup_admin"
else
  echo "    LOI: main.py chua load vps-backup — can pull code moi"
fi

echo "==> Import vps_backup_admin (backend/.venv, cwd=backend)"
if [[ -x "${BACKEND}/.venv/bin/python" ]]; then
  if ! (cd "${BACKEND}" && "${BACKEND}/.venv/bin/python" -c "import app.api.endpoints.vps_backup_admin as m; print('OK routes', len(m.router.routes))" 2>&1); then
    echo "    LOI: import vps_backup_admin that bai — xem traceback o tren"
  fi
else
  echo "    (bo qua — khong co backend/.venv/bin/python)"
fi

echo "==> Routes vps-backup trong main:app (cwd=backend)"
if [[ -x "${BACKEND}/.venv/bin/python" ]]; then
  if ! (cd "${BACKEND}" && "${BACKEND}/.venv/bin/python" -c "
from main import app
paths = sorted({getattr(r, 'path', '') for r in app.routes if getattr(r, 'path', None) and 'vps-backup' in getattr(r, 'path', '')})
print('So route vps-backup:', len(paths))
for p in paths:
    print(' ', p)
if not paths:
    raise SystemExit('LOI: 0 route vps-backup trong main:app')
" 2>&1); then
    echo "    (xem loi import o tren; pm2 logs 188-api --lines 80 --nostream)"
  fi
else
  echo "    (bo qua — khong co backend/.venv/bin/python)"
fi

echo "==> HTTP (${BASE})"
health=$(http_code "${BASE}/health")
echo "    health: ${health}"
admin_check=$(http_code "${BASE}/api/v1/admin/check-setup")
echo "    admin/check-setup (khong token): ${admin_check}"

if [[ "${health}" == "000" ]]; then
  echo ""
  echo "LOI: Khong ket noi port ${PORT}. Chay: bash deploy/fix-api-health.sh"
  exit 1
fi

ok=1
for path in \
  "/api/v1/admin/vps-backup/settings" \
  "/api/v1/admin/vps-backup/runs" \
  "/api/v1/admin/vps-backup/archives"
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
if [[ "${admin_check}" == "401" || "${admin_check}" == "403" || "${admin_check}" == "200" ]]; then
  echo "LOI: admin chay nhung vps-backup 404 — module vps_backup_admin chua load."
  echo "  pm2 logs 188-api --lines 120 --nostream | grep -iE 'vps_backup|failed|Import|Traceback' | tail -30"
else
  echo "LOI: admin cung khong load (${admin_check}) — xem pm2 logs 188-api khi khoi dong."
  echo "  pm2 logs 188-api --lines 120 --nostream | grep -iE 'admin|failed|Import|Traceback' | tail -30"
fi
echo ""
echo "Sua nhanh (mat thay doi local tren VPS neu co):"
echo "  cd ${ROOT}"
echo "  git fetch origin && git reset --hard origin/main"
echo "  pm2 delete 188-api 2>/dev/null; pm2 start deploy/ecosystem.config.cjs --only 188-api"
echo "  sleep 8 && bash deploy/verify-vps-backup-api.sh"
exit 1
