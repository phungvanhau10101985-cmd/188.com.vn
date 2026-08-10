#!/usr/bin/env bash
# Đặt biến .env an toàn cho storefront + cho phép job bản địa hóa ảnh tiếp tục sau deploy/restart.
# Tắt resume một lần (vd. sau cancel job): DEPLOY_DISABLE_IMAGE_LOCALIZATION_RESUME=1
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

IL_RESUME="${DEPLOY_DISABLE_IMAGE_LOCALIZATION_RESUME:-0}"
if [[ "${IL_RESUME}" == "1" ]]; then
  upsert IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP false "${ENV_FILE}"
else
  upsert IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP true "${ENV_FILE}"
fi
upsert RUN_DB_INIT_ON_STARTUP               0       "${ENV_FILE}"
upsert LEGACY_OOS_DEEPSEEK_ENABLED           false   "${ENV_FILE}"
upsert GROUP_LISTING_SKIP_SLOW_SLUG_POOL     true    "${ENV_FILE}"

if [[ "${IL_RESUME}" == "1" ]]; then
  echo "✓ API safe env: tắt resume job ảnh (DEPLOY_DISABLE_IMAGE_LOCALIZATION_RESUME=1); OOS redirect không gọi DeepSeek."
else
  echo "✓ API safe env: job bản địa hóa ảnh sẽ resume sau restart; OOS redirect không gọi DeepSeek."
fi
