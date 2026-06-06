#!/usr/bin/env bash
# Đặt biến .env an toàn cho storefront — tránh job ảnh/OCR resume khi restart API.
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ROOT}/backend/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "    (bỏ qua ensure-api-safe-env — chưa có ${ENV_FILE})"
  exit 0
fi

cp -a "${ENV_FILE}" "${ENV_FILE}.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

upsert() {
  local key="$1" val="$2" file="$3"
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}=.*|${key}=${val}|" "$file"
    echo "→ updated ${key}=${val}"
  else
    printf '\n%s=%s\n' "$key" "$val" >> "$file"
    echo "+ added   ${key}=${val}"
  fi
}

upsert IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP false "${ENV_FILE}"
upsert RUN_DB_INIT_ON_STARTUP               0       "${ENV_FILE}"

echo "✓ API safe env: không resume job ảnh/OCR khi khởi động."
