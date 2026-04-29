#!/usr/bin/env bash
# Cập nhật DATABASE_POOL_* trong backend/.env trên VPS, không đụng key khác.
# Idempotent: chạy nhiều lần kết quả như nhau. Tạo backup .env.bak-YYYYMMDD-HHMMSS.
#
# Dùng:
#   cd /var/www/188.com.vn
#   bash deploy/apply-db-pool.sh
#   pm2 restart 188-api --update-env && pm2 save

set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ROOT}/backend/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "✗ Không tìm thấy ${ENV_FILE} — tạo từ backend/.env.example trước."
  exit 1
fi

cp -a "$ENV_FILE" "${ENV_FILE}.bak-$(date +%Y%m%d-%H%M%S)"

# upsert KEY=VALUE (không đụng comment / blank lines)
upsert() {
  local key="$1" val="$2" file="$3"
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    # ưu tiên dùng tab '|' trong sed để tránh đụng '/' trong value (không cần ở đây nhưng an toàn)
    sed -i -E "s|^[[:space:]]*${key}=.*|${key}=${val}|" "$file"
    echo "→ updated ${key}=${val}"
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$file"
    echo "+ added   ${key}=${val}"
  fi
}

upsert DATABASE_POOL_SIZE     30   "$ENV_FILE"
upsert DATABASE_MAX_OVERFLOW  60   "$ENV_FILE"
upsert DATABASE_POOL_TIMEOUT  30   "$ENV_FILE"
upsert DATABASE_POOL_RECYCLE  1800 "$ENV_FILE"

echo
echo "✓ Đã cập nhật ${ENV_FILE}. Backup: ${ENV_FILE}.bak-*"
echo "Bước tiếp:  pm2 restart 188-api --update-env && pm2 save && pm2 logs 188-api --lines 80"
