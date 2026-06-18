#!/usr/bin/env bash
# Cập nhật VPS_BACKUP_DRIVE_* trong backend/.env (folder ID đúng từ Google Drive URL).
#
# Dùng trên VPS:
#   cd /var/www/188.com.vn
#   bash deploy/apply-vps-backup-drive-env.sh
#   pm2 restart 188-api --update-env && pm2 save
#   cd backend && python scripts/test_vps_backup_drive_folder.py
#
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ROOT}/backend/.env"
FOLDER_ID="${VPS_BACKUP_DRIVE_FOLDER_ID:-1NE152YF63m-jk_5tb3AIGnzAtPEcaYYu}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "✗ Không tìm thấy ${ENV_FILE}"
  exit 1
fi

cp -a "$ENV_FILE" "${ENV_FILE}.bak-$(date +%Y%m%d-%H%M%S)"

upsert() {
  local key="$1" val="$2" file="$3"
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}=.*|${key}=${val}|" "$file"
    echo "→ updated ${key}=${val}"
  else
    printf '\n# VPS backup → Google Drive\n%s=%s\n' "$key" "$val" >> "$file"
    echo "+ added   ${key}=${val}"
  fi
}

OLD_WRONG="1NF152YF63m-jk_5tb3AlGnzAtPEcaYYu"
if grep -q "${OLD_WRONG}" "$ENV_FILE" 2>/dev/null; then
  echo "⚠️  Phát hiện folder ID sai (NF/AlG) — sẽ thay bằng ID đúng (NE/AIG)."
fi

upsert VPS_BACKUP_DRIVE_ENABLED true "$ENV_FILE"
upsert VPS_BACKUP_DRIVE_FOLDER_ID "$FOLDER_ID" "$ENV_FILE"
upsert VPS_BACKUP_DRIVE_KEEP_COUNT 2 "$ENV_FILE"

echo ""
echo "✓ ${ENV_FILE} — folder: ${FOLDER_ID}"
echo "  Share folder Editor cho client_email trong file JSON service account."
echo "  pm2 restart 188-api --update-env"
