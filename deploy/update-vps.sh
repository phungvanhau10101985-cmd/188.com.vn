#!/usr/bin/env bash
# Deploy / cập nhật 188.com.vn trên VPS — tương tự flow nanoai (git pull + build).
# Cùng máy với nanoai: KHÔNG dùng "pm2 stop all" — chỉ dừng process tên 188-*.
#
# Usage (từ root repo trên VPS):
#   cd /var/www/188.com.vn
#   NODE_BUILD_HEAP_MB=3072 DEPLOY_SKIP_LINT=1 bash ./deploy/update-vps.sh main
#
set -euo pipefail

BRANCH="${1:-main}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
FRONTEND="${PROJECT_ROOT}/frontend"
VENV="${BACKEND}/.venv"

PM2_API="${PM2_API_NAME:-188-api}"
PM2_WEB="${PM2_WEB_NAME:-188-web}"

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

echo ""
echo "==> Xong build. Khởi động lại PM2 (ví dụ):"
echo "    pm2 restart ${PM2_API} ${PM2_WEB}"
echo "    # hoặc lần đầu: xem HUONG_DAN_DEPLOY.md (uvicorn 8001, PORT=3001)"
echo ""
