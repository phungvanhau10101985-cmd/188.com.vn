#!/usr/bin/env bash
# Cập nhật DATABASE_POOL_* + cache menu/catalog trong backend/.env, không đụng key khác.
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

upsert DATABASE_POOL_SIZE                  8    "$ENV_FILE"
upsert DATABASE_MAX_OVERFLOW               12   "$ENV_FILE"
upsert DATABASE_POOL_TIMEOUT               20   "$ENV_FILE"
upsert DATABASE_POOL_RECYCLE               1800 "$ENV_FILE"
upsert CATEGORY_MENU_TREE_TTL_SECONDS      600  "$ENV_FILE"
upsert CATEGORY_CATALOG_TILES_TTL_SECONDS  600  "$ENV_FILE"
upsert SETTINGS_DB_PROBE_ON_LOAD           false "$ENV_FILE"

bash "${ROOT}/deploy/ensure-api-safe-env.sh" 2>/dev/null || true

echo
echo "✓ Đã cập nhật ${ENV_FILE}. Backup: ${ENV_FILE}.bak-*"
echo "Bước tiếp:  bash deploy/relieve-db-after-restart.sh"
echo "    hoặc:    pm2 restart 188-api --update-env && pm2 save"
