#!/usr/bin/env bash
# Sửa nhanh 188-web không listen :3001 (health curl → 000)
# Usage trên VPS:
#   cd /var/www/188.com.vn && bash deploy/fix-web-health.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="${PROJECT_ROOT}/frontend"
PM2_WEB="${PM2_WEB_NAME:-188-web}"
PORT="${WEB_INTERNAL_PORT:-3001}"

curl_http_code() {
  local url="$1"
  local code=""
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 10 "$url" 2>/dev/null) || true
  if [[ -z "${code}" ]]; then
    echo "000"
  else
    echo "${code}"
  fi
}

# Giải phóng cổng (next-server mồ côi sau crash / test tay — PM2 errored nhưng :3001 vẫn listen).
kill_listeners_on_port() {
  local port="$1"
  local killed=0
  if command -v fuser >/dev/null 2>&1; then
    if fuser "${port}/tcp" >/dev/null 2>&1; then
      echo "    fuser -k ${port}/tcp"
      fuser -k "${port}/tcp" 2>/dev/null || true
      killed=1
    fi
  else
    local line pid
    while IFS= read -r line; do
      pid=$(echo "$line" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
      [[ -z "${pid}" ]] && continue
      echo "    kill pid ${pid} (đang listen :${port})"
      kill "${pid}" 2>/dev/null || true
      killed=1
    done < <(ss -tlnp 2>/dev/null | grep ":${port}\\b" || true)
  fi
  if [[ "${killed}" == "1" ]]; then
    sleep 2
    while IFS= read -r line; do
      pid=$(echo "$line" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -1)
      [[ -z "${pid}" ]] && continue
      kill -9 "${pid}" 2>/dev/null || true
    done < <(ss -tlnp 2>/dev/null | grep ":${port}\\b" || true)
  fi
}

pm2_web_uses_legacy_launcher() {
  pm2 describe "${PM2_WEB}" 2>/dev/null | grep -q 'exec npm run start'
}

echo "==> 188-web health fix (port ${PORT})"
echo "    Project: ${PROJECT_ROOT}"

if [[ ! -d "${FRONTEND}" ]]; then
  echo "❌ Không thấy ${FRONTEND}"
  exit 1
fi

if [[ ! -d "${FRONTEND}/.next" ]]; then
  echo "❌ Thiếu frontend/.next — chạy build trước:"
  echo "   cd ${FRONTEND} && npm ci && npm run build"
  exit 1
fi

if [[ ! -f "${FRONTEND}/scripts/next-start.cjs" ]]; then
  echo "❌ Thiếu frontend/scripts/next-start.cjs"
  exit 1
fi

if [[ ! -f "${FRONTEND}/.next/BUILD_ID" ]]; then
  echo "❌ Thiếu frontend/.next/BUILD_ID — build chưa hoàn tất:"
  echo "   cd ${FRONTEND} && npm ci && npm run build"
  exit 1
fi

echo ""
echo "==> PM2 hiện tại"
pm2 describe "${PM2_WEB}" 2>/dev/null | grep -E 'status|restarts|cwd|script path|script args|error' || echo "(chưa có ${PM2_WEB})"
if pm2_web_uses_legacy_launcher; then
  echo "    ⚠️  PM2 vẫn dùng lệnh cũ (bash + npm run start) — sẽ tạo lại từ deploy/ecosystem.config.cjs"
fi

echo ""
echo "==> Cổng đang listen (trước khi dọn)"
ss -tlnp 2>/dev/null | grep -E ":(${PORT}|3000|3001)\\b" || echo "(chưa có Next trên ${PORT}/3000/3001)"

echo ""
echo "==> Dừng PM2 + giải phóng cổng ${PORT}"
pm2 stop "${PM2_WEB}" 2>/dev/null || true
pm2 delete "${PM2_WEB}" 2>/dev/null || true
kill_listeners_on_port "${PORT}"

echo ""
echo "==> Cổng sau khi dọn"
ss -tlnp 2>/dev/null | grep -E ":(${PORT}|3000|3001)\\b" || echo "(cổng ${PORT} trống — OK)"

echo ""
echo "==> Khởi động ${PM2_WEB} từ deploy/ecosystem.config.cjs (node scripts/next-start.cjs)"
cd "${PROJECT_ROOT}"
pm2 start deploy/ecosystem.config.cjs --only "${PM2_WEB}"
pm2 save || true

echo ""
echo "==> Chờ Web (tối đa 60s, GET /robots.txt — không SSR trang chủ)..."
code="000"
for _i in $(seq 1 60); do
  code=$(curl_http_code "http://127.0.0.1:${PORT}/robots.txt")
  if [[ "${code}" == "200" || "${code}" == "204" ]]; then
    break
  fi
  sleep 1
done

echo "    GET http://127.0.0.1:${PORT}/robots.txt → ${code}"

if [[ "${code}" != "200" && "${code}" != "204" ]]; then
  echo ""
  echo "❌ Vẫn không healthy. Log lỗi:"
  pm2 logs "${PM2_WEB}" --lines 80 --nostream 2>/dev/null || true
  echo ""
  echo "Thử chạy tay (debug):"
  echo "  cd ${FRONTEND} && node scripts/next-start.cjs"
  exit 1
fi

echo "✅ 188-web OK trên port ${PORT}"
