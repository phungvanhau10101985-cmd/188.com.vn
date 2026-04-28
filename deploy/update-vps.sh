#!/usr/bin/env bash
# Deploy / cập nhật 188.com.vn trên VPS — tương tự flow nanoai (git pull + build).
# Cùng máy với nanoai: KHÔNG dùng "pm2 stop all" — chỉ dừng process tên 188-*.
#
# Usage (từ root repo trên VPS):
#   cd /var/www/188.com.vn
#   DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
#
# Biến tuỳ chọn:
#   PM2_API_NAME / PM2_WEB_NAME   (mặc định 188-api, 188-web)
#   API_INTERNAL_PORT             (mặc định 8001 — Uvicorn FastAPI)
#   WEB_INTERNAL_PORT             (mặc định 3001 — Next start)
#   DEPLOY_RESTART_PM2=0          bỏ qua pm2 restart sau build
#   DEPLOY_STRICT_HEALTH=1        exit 1 nếu curl health không 200
#
set -euo pipefail

BRANCH="${1:-main}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
FRONTEND="${PROJECT_ROOT}/frontend"
VENV="${BACKEND}/.venv"

PM2_API="${PM2_API_NAME:-188-api}"
PM2_WEB="${PM2_WEB_NAME:-188-web}"
API_INTERNAL_PORT="${API_INTERNAL_PORT:-8001}"
WEB_INTERNAL_PORT="${WEB_INTERNAL_PORT:-3001}"

cd "${PROJECT_ROOT}"

if [[ "${DEPLOY_STOP_PM2_BEFORE_BUILD:-0}" == "1" ]]; then
  echo "==> PM2 stop: ${PM2_API} ${PM2_WEB}"
  pm2 stop "${PM2_API}" 2>/dev/null || true
  pm2 stop "${PM2_WEB}" 2>/dev/null || true
fi

echo "==> git pull origin ${BRANCH}"
git pull origin "${BRANCH}"

echo "==> Backend: venv + pip"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi
# shellcheck disable=SC1090
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
pip install -r "${BACKEND}/requirements.txt"

cd "${BACKEND}"
if [[ "${DEPLOY_SKIP_DB_INIT:-0}" != "1" ]]; then
  set +e
  python -c "from main import init_database_tables; init_database_tables()"
  set -e
fi
deactivate

if [[ "${DEPLOY_BUILD_VPS:-1}" != "1" ]]; then
  echo "DEPLOY_BUILD_VPS=0 — bỏ qua frontend build. Kết thúc."
  exit 0
fi

echo "==> Frontend: xóa .next (nếu có)"
rm -rf "${FRONTEND}/.next"

HEAP="${NODE_BUILD_HEAP_MB:-3072}"
export NODE_OPTIONS="--max-old-space-size=${HEAP}"

cd "${FRONTEND}"
npm ci

if [[ "${DEPLOY_SKIP_LINT:-0}" == "1" ]]; then
  echo "==> next build (bỏ qua lint nếu Next hỗ trợ --no-lint)"
  npx next build --no-lint 2>/dev/null || npm run build
else
  npm run build
fi

if [[ "${DEPLOY_SKIP_TYPECHECK:-0}" == "1" ]]; then
  echo "==> Lưu ý: DEPLOY_SKIP_TYPECHECK=1 không tự tắt TS — cần ignoreBuildErrors trong next.config nếu muốn bỏ qua lỗi type."
fi

health_check_local() {
  echo ""
  echo "==> Kiểm tra sức khỏe service (localhost, sau PM2 restart)"
  local api_code web_code
  api_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${API_INTERNAL_PORT}/health" 2>/dev/null || echo "000")
  web_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${WEB_INTERNAL_PORT}/" 2>/dev/null || echo "000")
  echo "    GET http://127.0.0.1:${API_INTERNAL_PORT}/health  → ${api_code}"
  echo "    GET http://127.0.0.1:${WEB_INTERNAL_PORT}/           → ${web_code}"
  if [[ "${api_code}" == "200" && "${web_code}" == "200" ]]; then
    echo "✅ Sức khỏe: OK."
    return 0
  fi
  echo "⚠️  Sức khỏe bất thường — xem: pm2 logs ${PM2_API} | pm2 logs ${PM2_WEB}"
  [[ "${DEPLOY_STRICT_HEALTH:-0}" == "1" ]] && return 1
  return 0
}

if [[ "${DEPLOY_RESTART_PM2:-1}" != "1" ]]; then
  echo ""
  echo "==> DEPLOY_RESTART_PM2=0 — không restart PM2. Chạy tay: pm2 restart ${PM2_API} ${PM2_WEB}"
  health_check_local || true
  exit 0
fi

echo ""
echo "==> PM2: khởi động lại ${PM2_API} và ${PM2_WEB}"
if pm2 describe "${PM2_API}" &>/dev/null && pm2 describe "${PM2_WEB}" &>/dev/null; then
  pm2 restart "${PM2_API}" "${PM2_WEB}"
  pm2 save || true
  sleep 3
else
  echo "⚠️  Chưa có process ${PM2_API} / ${PM2_WEB} — bỏ qua restart (tạo lần đầu: xem HUONG_DAN_DEPLOY.md)."
fi

health_check_local

echo ""
echo "==> Deploy xong."
