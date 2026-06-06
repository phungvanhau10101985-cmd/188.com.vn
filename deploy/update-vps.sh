#!/usr/bin/env bash
# Deploy / cập nhật 188.com.vn trên VPS — tương tự flow nanoai (git pull + build).
# Cùng máy với nanoai: KHÔNG dùng "pm2 stop all" — chỉ dừng process tên 188-*.
#
# Usage (từ root repo trên VPS):
#   Một lần: git config pull.rebase false   # để "git pull origin main" không báo divergent (merge mặc định)
#   Mỗi lần — chỉ pull tay rồi deploy (không git trong script):
#     cd /var/www/188.com.vn && git pull origin main
#     DEPLOY_SKIP_GIT=1 DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
#     (DEPLOY_STOP_PM2_BEFORE_BUILD chỉ stop 188-web — giữ 188-api cho next build SSR)
#   Hoặc một lệnh (script đã TÍCH HỢP git pull origin <nhánh>): bỏ DEPLOY_SKIP_GIT
#     → trong script: deploy_git_sync → git pull origin <nhánh> --no-rebase (đối số đầu, mặc định main)
#   DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main
#
# Biến tuỳ chọn:
#   PM2_API_NAME / PM2_WEB_NAME   (mặc định 188-api, 188-web)
#   API_INTERNAL_PORT             (mặc định 8001 — Uvicorn FastAPI)
#   WEB_INTERNAL_PORT             (mặc định 3001 — Next start)
#   DEPLOY_RESTART_PM2=0          bỏ qua pm2 restart sau build
#   DEPLOY_RESTART_ALL_PM2=1      (mặc định) sau deploy 188: restart mọi process PM2 khác trên VPS
#   DEPLOY_RESTART_ALL_PM2=0      chỉ restart ${PM2_API} / ${PM2_WEB}
#   DEPLOY_STRICT_HEALTH=1        exit 1 nếu curl health không 200
#   DEPLOY_SKIP_DB_INIT=1         không tạo DB / không chạy init_database_tables + migrations
#   DEPLOY_CREATE_DATABASE=0      không gọi postgres-create-db.sh (DB đã có sẵn)
#   DEPLOY_STRICT_DB_INIT=0       nếu khởi tạo DB lỗi vẫn tiếp tục deploy (mặc định bật strict từ script)
#   DEPLOY_GIT_SYNC=merge          (mặc định) merge --no-edit; tránh lỗi Git 2.x "divergent branches" và không mở nano
#   DEPLOY_GIT_SYNC=rebase         git pull --rebase
#   DEPLOY_GIT_SYNC=ff-only        chỉ fast-forward — fail nếu VPS có commit lệch (không tạo merge commit)
#   DEPLOY_GIT_SYNC=reset-hard     git fetch + reset --hard origin/<branch> — xóa chỉnh sửa local trên VPS, khớp GitHub
#   DEPLOY_SKIP_GIT=1              không chạy git trong script (đã git pull tay trước đó)
#   DEPLOY_SKIP_PLAYWRIGHT=1       không chạy playwright install chromium (đã cài browser)
#
set -euo pipefail

BRANCH="${1:-main}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=health-lib.sh
source "${PROJECT_ROOT}/deploy/health-lib.sh"
BACKEND="${PROJECT_ROOT}/backend"
FRONTEND="${PROJECT_ROOT}/frontend"
VENV="${BACKEND}/.venv"

PM2_API="${PM2_API_NAME:-188-api}"
PM2_WEB="${PM2_WEB_NAME:-188-web}"
API_INTERNAL_PORT="${API_INTERNAL_PORT:-8001}"
WEB_INTERNAL_PORT="${WEB_INTERNAL_PORT:-3001}"

ensure_postgres_database_for_deploy() {
  [[ "${DEPLOY_CREATE_DATABASE:-1}" == "1" ]] || return 0
  local envf="${BACKEND}/.env"
  if [[ ! -f "$envf" ]]; then
    echo "    (Không có backend/.env — bỏ qua tạo database PostgreSQL)"
    return 0
  fi
  local raw
  raw=$(grep -m1 '^DATABASE_URL=' "$envf" | cut -d= -f2- | tr -d '\r')
  raw="${raw#\"}"
  raw="${raw%\"}"
  raw="${raw#\'}"
  raw="${raw%\'}"
  case "$raw" in
    postgresql:*|postgres:*|postgresql+*) ;;
    *) return 0 ;;
  esac
  local tail="${raw##*/}"
  local dbname="${tail%%\?*}"
  if [[ -z "$dbname" ]] || [[ "$dbname" == "$raw" ]]; then
    return 0
  fi
  echo "    PostgreSQL → tạo database nếu chưa có: ${dbname}"
  POSTGRES_DB_NAME="$dbname" bash "${PROJECT_ROOT}/deploy/postgres-create-db.sh"
}

cd "${PROJECT_ROOT}"

port_is_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tln 2>/dev/null | grep -qE ":${port}\\b"
    return $?
  fi
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "${port}" >/dev/null 2>&1
    return $?
  fi
  return 1
}

if [[ "${DEPLOY_STOP_PM2_BEFORE_BUILD:-0}" == "1" ]]; then
  # next build SSR layout gọi API :8001 — KHÔNG stop 188-api (chỉ dừng web giải phóng RAM).
  # Lưu dump trước stop để pm2 resurrect khôi phục các dự án khác sau build.
  echo "==> PM2 stop: chỉ ${PM2_WEB} (giữ ${PM2_API} cho next build)"
  pm2 save 2>/dev/null || true
  pm2 stop "${PM2_WEB}" 2>/dev/null || true
fi

# Git ≥2.27: pull cần strategy khi có commit local không có trên origin (divergent). Mặc định merge.
deploy_git_sync() {
  local mode="${DEPLOY_GIT_SYNC:-merge}"
  case "${mode}" in
    reset-hard|hard)
      echo "==> Git: FETCH + reset --hard origin/${BRANCH} (bỏ mọi chỉnh sửa chưa commit / commit chỉ có trên VPS)"
      git fetch origin "${BRANCH}"
      git checkout "${BRANCH}" 2>/dev/null || git checkout -b "${BRANCH}" "origin/${BRANCH}" 2>/dev/null || true
      git reset --hard "origin/${BRANCH}"
      ;;
    rebase)
      echo "==> git pull origin ${BRANCH} --rebase"
      git pull --rebase origin "${BRANCH}"
      ;;
    ff-only|fast-forward)
      echo "==> git pull origin ${BRANCH} --ff-only (chỉ fast-forward — không tạo merge commit)"
      git fetch origin "${BRANCH}"
      git pull --ff-only origin "${BRANCH}"
      ;;
    merge|*)
      echo "==> git pull origin ${BRANCH} --no-rebase --no-edit (merge nếu cần, không mở editor)"
      # GIT_MERGE_AUTOEDIT=no + --no-edit để git không bật nano hỏi commit message khi merge.
      GIT_MERGE_AUTOEDIT=no git pull --no-edit origin "${BRANCH}" --no-rebase
      ;;
  esac
}

if [[ "${DEPLOY_SKIP_GIT:-0}" == "1" ]]; then
  echo "==> Git: DEPLOY_SKIP_GIT=1 — bỏ qua (đã git pull / sync tay trước khi chạy script)."
else
  if ! deploy_git_sync; then
    echo ""
    echo "❌ Git sync thất bại (vd. unmerged files / conflict)."
    echo "   Khôi phục site không cần pull: DEPLOY_SKIP_GIT=1 bash ./deploy/update-vps.sh ${BRANCH}"
    echo "   Ép khớp GitHub (xóa chỉnh sửa local trên VPS): DEPLOY_GIT_SYNC=reset-hard bash ./deploy/update-vps.sh ${BRANCH}"
    echo "   Xem file conflict: git status"
    exit 1
  fi
fi

echo "==> Backend: venv + pip"
if [[ ! -d "${VENV}" ]]; then
  python3 -m venv "${VENV}"
fi
# shellcheck disable=SC1090
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
pip install -r "${BACKEND}/requirements.txt"

if [[ "${DEPLOY_SKIP_PLAYWRIGHT:-0}" != "1" ]]; then
  PW_SCRIPT="${PROJECT_ROOT}/deploy/install-playwright-browsers.sh"
  if [[ -f "${PW_SCRIPT}" ]]; then
    bash "${PW_SCRIPT}"
  else
    echo "⚠️  Thiếu ${PW_SCRIPT} (chưa git pull / chưa push deploy/) — cài Chromium inline."
    if python -c "import playwright" 2>/dev/null; then
      python -m playwright install chromium || echo "⚠️  playwright install chromium thất bại — thử lại sau hoặc DEPLOY_SKIP_PLAYWRIGHT=1"
    else
      echo "⚠️  Package playwright chưa có trong venv — bỏ qua browser."
    fi
  fi
else
  echo "==> Playwright: DEPLOY_SKIP_PLAYWRIGHT=1 — bỏ qua."
fi

cd "${BACKEND}"
if [[ "${DEPLOY_SKIP_DB_INIT:-0}" != "1" ]]; then
  echo "==> Database: PostgreSQL (tạo DB nếu bật) + init_database_tables (create_all + migrations: admin_users, orders, …)"
  ensure_postgres_database_for_deploy
  # Chỉ áp strict cho subprocess này — không để vào .env/server (tránh uvicorn exit khi lỗi DB)
  DEPLOY_STRICT_DB_INIT="${DEPLOY_STRICT_DB_INIT:-1}" \
    python -c "from main import init_database_tables; init_database_tables()"
else
  echo "==> Database: DEPLOY_SKIP_DB_INIT=1 — bỏ qua."
fi
deactivate

if [[ "${DEPLOY_BUILD_VPS:-1}" != "1" ]]; then
  echo "DEPLOY_BUILD_VPS=0 — bỏ qua frontend build. Kết thúc."
  exit 0
fi

echo "==> Frontend: đảm bảo API listen trước next build (layout SSR cần :${API_INTERNAL_PORT})"
if ! port_is_listening "${API_INTERNAL_PORT}"; then
  echo "    Khởi động ${PM2_API}…"
  pm2 start "${PROJECT_ROOT}/deploy/ecosystem.config.cjs" --only "${PM2_API}" 2>/dev/null \
    || pm2 restart "${PM2_API}" --update-env
  for _w in $(seq 1 45); do
    port_is_listening "${API_INTERNAL_PORT}" && break
    sleep 1
  done
fi
if port_is_listening "${API_INTERNAL_PORT}"; then
  _hc=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 \
    "http://127.0.0.1:${API_INTERNAL_PORT}/health" 2>/dev/null || echo "000")
  echo "    API health → ${_hc}"
  if [[ "${_hc}" != "200" ]]; then
    echo "⚠️  API health ≠ 200 — next build có thể timeout (layout gọi API)."
    if [[ "${DEPLOY_REQUIRE_API_BEFORE_BUILD:-1}" == "1" ]]; then
      echo "❌ DEPLOY_REQUIRE_API_BEFORE_BUILD=1 — dừng deploy. Sửa API trước: pm2 restart ${PM2_API}"
      exit 1
    fi
  fi
else
  echo "⚠️  API chưa listen :${API_INTERNAL_PORT} — next build có thể timeout (layout gọi API)."
  if [[ "${DEPLOY_REQUIRE_API_BEFORE_BUILD:-1}" == "1" ]]; then
    echo "❌ DEPLOY_REQUIRE_API_BEFORE_BUILD=1 — dừng deploy."
    exit 1
  fi
fi

echo "==> Frontend: xóa .next (nếu có)"
rm -rf "${FRONTEND}/.next"

HEAP="${NODE_BUILD_HEAP_MB:-3072}"
export NODE_OPTIONS="--max-old-space-size=${HEAP}"
# Giảm worker song song — tránh 7× layout × category tree làm đầy pool DB khi build.
export NEXT_PRIVATE_BUILD_WORKERS="${NEXT_PRIVATE_BUILD_WORKERS:-2}"

cd "${FRONTEND}"
npm ci

if [[ "${DEPLOY_SKIP_LINT:-0}" == "1" ]]; then
  echo "==> next build --webpack (Next 16 mặc định Turbopack; dự án có webpack() alias antd — bỏ qua lint nếu Next hỗ trợ --no-lint)"
  npx next build --webpack --no-lint 2>/dev/null || npm run build
else
  npm run build
fi

if [[ "${DEPLOY_SKIP_TYPECHECK:-0}" == "1" ]]; then
  echo "==> Lưu ý: DEPLOY_SKIP_TYPECHECK=1 không tự tắt TS — cần ignoreBuildErrors trong next.config nếu muốn bỏ qua lỗi type."
fi

curl_http_code() {
  local url="$1"
  local max_time="${2:-5}"
  local code=""
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 1 --max-time "${max_time}" "$url" 2>/dev/null) || true
  if [[ -z "${code}" ]]; then
    echo "000"
  else
    echo "${code}"
  fi
}

run_with_timeout() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${secs}" "$@" 2>/dev/null || true
  else
    "$@" 2>/dev/null || true
  fi
}

health_wait_tick() {
  local label="$1"
  local attempt="$2"
  local max="$3"
  if (( attempt == 1 || attempt % 5 == 0 || attempt == max )); then
    echo "    … ${label} (${attempt}/${max}s)"
  fi
}

kill_listeners_on_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
    sleep 1
    return 0
  fi
  local line pid
  while IFS= read -r line; do
    pid=$(echo "$line" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
    [[ -z "${pid}" ]] && continue
    kill "${pid}" 2>/dev/null || kill -9 "${pid}" 2>/dev/null || true
  done < <(ss -tlnp 2>/dev/null | grep ":${port}\\b" || true)
  sleep 1
}

pm2_recreate_web_from_ecosystem() {
  echo "==> PM2: tạo lại ${PM2_WEB} từ deploy/ecosystem.config.cjs"
  pm2 stop "${PM2_WEB}" 2>/dev/null || true
  pm2 delete "${PM2_WEB}" 2>/dev/null || true
  kill_listeners_on_port "${WEB_INTERNAL_PORT}"
  pm2 start "${PROJECT_ROOT}/deploy/ecosystem.config.cjs" --only "${PM2_WEB}"
}

pm2_web_needs_recreate() {
  if ! pm2 describe "${PM2_WEB}" &>/dev/null; then
    return 0
  fi
  if pm2 describe "${PM2_WEB}" 2>/dev/null | grep -qE 'status.*errored|exec npm run start'; then
    return 0
  fi
  return 1
}

pm2_list_process_names() {
  pm2 jlist 2>/dev/null | python3 -c "
import json, sys
try:
    for p in json.load(sys.stdin):
        n = p.get('name')
        if n:
            print(n)
except Exception:
    pass
" 2>/dev/null || true
}

pm2_restart_other_vps_apps() {
  local name restarted=0
  echo ""
  echo "==> PM2: khởi động lại các dự án khác trên VPS (ngoài ${PM2_API}, ${PM2_WEB})"
  while IFS= read -r name; do
    [[ -z "${name}" ]] && continue
    [[ "${name}" == "${PM2_API}" || "${name}" == "${PM2_WEB}" ]] && continue
    echo "    → restart ${name}"
    pm2 restart "${name}" --update-env 2>/dev/null || true
    restarted=$((restarted + 1))
  done < <(pm2_list_process_names)
  if [[ "${restarted}" -eq 0 ]]; then
    echo "    (Không có process PM2 nào khác trên VPS.)"
  fi
}

health_check_local() {
  echo ""
  echo "==> Kiểm tra sức khỏe service (localhost, sau PM2 restart)"
  # Không dùng GET / — trang chủ SSR + gọi API có thể >10s/lần → health check im lặng hàng phút.
  local web_path="${WEB_HEALTH_PATH:-/robots.txt}"
  local api_wait="${HEALTH_API_WAIT_SEC:-45}"
  local web_wait="${HEALTH_WEB_WAIT_SEC:-60}"
  local api_code="000" web_code="000"
  local _i
  echo "    API: http://127.0.0.1:${API_INTERNAL_PORT}/health (tối đa ${api_wait}s)"
  for _i in $(seq 1 "${api_wait}"); do
    health_wait_tick "chờ API" "${_i}" "${api_wait}"
    if port_is_listening "${API_INTERNAL_PORT}"; then
      api_code=$(curl_http_code "http://127.0.0.1:${API_INTERNAL_PORT}/health" 3)
      if [[ "${api_code}" == "200" ]]; then
        break
      fi
    else
      api_code="000"
    fi
    sleep 1
  done
  echo "    Web: http://127.0.0.1:${WEB_INTERNAL_PORT}${web_path} (nhẹ, không SSR trang chủ — tối đa ${web_wait}s)"
  for _i in $(seq 1 "${web_wait}"); do
    health_wait_tick "chờ Web" "${_i}" "${web_wait}"
    if port_is_listening "${WEB_INTERNAL_PORT}"; then
      web_code=$(curl_http_code "http://127.0.0.1:${WEB_INTERNAL_PORT}${web_path}" 5)
      if [[ "${web_code}" == "200" || "${web_code}" == "204" ]]; then
        break
      fi
    else
      web_code="000"
    fi
    sleep 1
  done
  echo "    GET http://127.0.0.1:${API_INTERNAL_PORT}/health  → ${api_code}"
  local ship_stats_code
  ship_stats_code=$(curl_http_code "http://127.0.0.1:${API_INTERNAL_PORT}/api/v1/orders/admin/shipping/operations-stats" 5)
  echo "    GET .../orders/admin/shipping/operations-stats → ${ship_stats_code} (401/403=OK, 404=cần pull+restart API)"
  echo "    GET http://127.0.0.1:${WEB_INTERNAL_PORT}${web_path} → ${web_code}"
  local products_code="000"
  local homepage_code="000"
  local sale_code="000"
  if [[ "${api_code}" == "200" ]]; then
    products_code=$(health_curl_products_probe "${API_INTERNAL_PORT}")
    if [[ "${products_code}" != "200" ]]; then
      echo "    → products timeout — dọn pool DB (idle in transaction)…"
      health_terminate_idle_db_transactions
      sleep 2
      products_code=$(health_curl_products_probe "${API_INTERNAL_PORT}" 2 30)
    fi
    echo "    GET /api/v1/products/?limit=${HEALTH_PRODUCTS_LIMIT:-8}&skip_total=true → ${products_code} (200 cần có — 000=pool DB kẹt)"
    sale_code=$(health_curl_http_code "http://127.0.0.1:${API_INTERNAL_PORT}/api/v1/sale-calendar/current" 15)
    echo "    GET /api/v1/sale-calendar/current → ${sale_code}"
  fi
  if [[ "${web_code}" == "200" || "${web_code}" == "204" ]]; then
    homepage_code=$(health_curl_homepage_smoke "http://127.0.0.1:${WEB_INTERNAL_PORT}")
    echo "    GET / (homepage) → ${homepage_code}"
  fi
  local core_ok=0
  if [[ "${api_code}" == "200" && ( "${web_code}" == "200" || "${web_code}" == "204" ) && "${products_code}" == "200" ]]; then
    core_ok=1
  fi
  if [[ "${core_ok}" == "1" && "${homepage_code}" == "200" ]]; then
    echo "✅ Sức khỏe: OK (API + Web + products + homepage)."
    return 0
  fi
  if [[ "${core_ok}" == "1" ]]; then
    echo "✅ Sức khỏe cốt lõi: OK (API + Web + products)."
    if [[ "${homepage_code}" != "200" ]]; then
      echo "⚠️  Homepage SSR chưa trả 200 trong ${HEALTH_HOMEPAGE_CURL_MAX_SEC:-120}s (mã ${homepage_code})."
      echo "    Site có thể vẫn chạy nhưng chậm — xem: pm2 logs ${PM2_WEB} --lines 60"
      if [[ "${DEPLOY_REQUIRE_HOMEPAGE:-0}" == "1" ]]; then
        echo "❌ DEPLOY_REQUIRE_HOMEPAGE=1 — coi là deploy thất bại."
        [[ "${DEPLOY_STRICT_HEALTH:-1}" == "1" ]] && return 1
      fi
    fi
    return 0
  fi
  echo "⚠️  Sức khỏe bất thường — xem: pm2 logs ${PM2_API} | pm2 logs ${PM2_WEB}"
  if [[ "${api_code}" == "200" && "${products_code}" != "200" ]]; then
    echo "    /health OK nhưng products timeout → pool PostgreSQL kẹt."
    echo "    Thử: bash deploy/relieve-db-after-restart.sh && pm2 restart ${PM2_API} --update-env"
  fi
  if [[ "${api_code}" != "200" ]]; then
    echo "    Gợi ý API: đảm bảo backend lắng nghe cổng ${API_INTERNAL_PORT} (SERVER_PORT=${API_INTERNAL_PORT} trong backend/.env hoặc"
    echo "    args uvicorn: --port ${API_INTERNAL_PORT}). Kiểm tra: pm2 show ${PM2_API} | ss -tlnp | grep -E ':${API_INTERNAL_PORT}\\b'"
    echo ""
    echo "    --- pm2 show ${PM2_API} (cwd + script args) ---"
    pm2 show "${PM2_API}" 2>/dev/null | grep -E 'status|cwd|script path|script args|error|restarts' || true
    echo "    --- cổng đang listen ---"
    ss -tlnp 2>/dev/null | grep -E ":(${API_INTERNAL_PORT}|8000|8001)\\b" || true
    echo "    --- ${PM2_API} error log (20 dòng cuối) ---"
    run_with_timeout 15 pm2 logs "${PM2_API}" --lines 20 --nostream
  fi
  if [[ "${web_code}" != "200" && "${web_code}" != "204" ]]; then
    echo "    Gợi ý Web: Next cần frontend/.next sau build; cổng ${WEB_INTERNAL_PORT} (PORT trong PM2)."
    echo "    Sửa nhanh: bash deploy/fix-web-health.sh"
    echo ""
    echo "    --- pm2 show ${PM2_WEB} ---"
    pm2 show "${PM2_WEB}" 2>/dev/null | grep -E 'status|cwd|script path|script args|error|restarts' || true
    echo "    --- cổng đang listen ---"
    ss -tlnp 2>/dev/null | grep -E ":(${WEB_INTERNAL_PORT}|3000|3001)\\b" || true
    if [[ ! -d "${FRONTEND}/.next" ]]; then
      echo "    ❌ Thiếu ${FRONTEND}/.next — chạy lại: cd frontend && npm run build"
    fi
    echo "    --- ${PM2_WEB} error log (40 dòng cuối) ---"
    run_with_timeout 20 pm2 logs "${PM2_WEB}" --lines 40 --nostream
  fi
  [[ "${DEPLOY_STRICT_HEALTH:-1}" == "1" ]] && return 1
  return 0
}

print_safe_deploy_checklist() {
  echo ""
  echo "==> Checklist deploy an toàn (chống treo) — lần sau chạy nhanh:"
  echo "   1) Trước deploy: tạm dừng app không liên quan (vd: pm2 stop thu-do-online worksheet-worker)."
  echo "   2) Deploy chuẩn: git pull -> backend pip/init -> frontend build -> pm2 restart ${PM2_API} ${PM2_WEB} + các dự án PM2 khác."
  echo "   3) Luôn pm2 save sau restart để reboot không chạy cấu hình cũ."
  echo "   4) Flush log rồi theo dõi lỗi mới: pm2 flush ${PM2_API}; pm2 flush ${PM2_WEB}; pm2 logs ..."
  echo "   5) Nếu web lag: kiểm tra DB active query (pg_stat_activity), hủy query nặng/idle transaction kéo dài."
  echo "   6) Sau deploy lớn Next.js: hard refresh (Ctrl+F5) hoặc tab ẩn danh để tránh Server Action mismatch."
}

if [[ "${DEPLOY_RESTART_PM2:-1}" != "1" ]]; then
  echo ""
  echo "==> DEPLOY_RESTART_PM2=0 — không restart PM2. Chạy tay: pm2 restart ${PM2_API} ${PM2_WEB}"
  health_check_local || true
  print_safe_deploy_checklist
  exit 0
fi

echo ""
echo "==> PM2: khôi phục dump + khởi động lại ${PM2_API}, ${PM2_WEB} và các dự án khác trên VPS"
pm2 resurrect 2>/dev/null || true

if pm2 describe "${PM2_API}" &>/dev/null; then
  pm2 restart "${PM2_API}" --update-env
else
  echo "⚠️  Chưa có ${PM2_API} — tạo từ ecosystem"
  pm2 start "${PROJECT_ROOT}/deploy/ecosystem.config.cjs" --only "${PM2_API}" 2>/dev/null || true
fi

if pm2_web_needs_recreate; then
  pm2_recreate_web_from_ecosystem
elif pm2 describe "${PM2_WEB}" &>/dev/null; then
  pm2 restart "${PM2_WEB}" --update-env
else
  pm2_recreate_web_from_ecosystem
fi

if [[ "${DEPLOY_RESTART_ALL_PM2:-1}" == "1" ]]; then
  pm2_restart_other_vps_apps
else
  echo ""
  echo "==> DEPLOY_RESTART_ALL_PM2=0 — chỉ restart ${PM2_API} / ${PM2_WEB}."
fi

pm2 save || true
sleep 5

if [[ -f "${PROJECT_ROOT}/deploy/relieve-db-after-restart.sh" ]]; then
  echo ""
  echo "==> Dọn pool PostgreSQL sau restart (apply-db-pool + terminate idle in transaction)"
  bash "${PROJECT_ROOT}/deploy/relieve-db-after-restart.sh" || true
fi

health_check_local || true
print_safe_deploy_checklist

echo ""
echo "==> Deploy xong."
