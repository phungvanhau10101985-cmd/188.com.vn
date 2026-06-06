#!/usr/bin/env bash
# Bật đồng bộ sản phẩm (41 cột) lên Google Sheet + cron 3:30 sáng giờ VN.
# Chạy trên VPS: cd /var/www/188.com.vn && bash deploy/enable-product-catalog-sheet-sync.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/backend/.env"
API_HOST="${API_HOST:-188.com.vn}"
CRON_LINE='30 3 * * * curl -sS -m 3600 -H "Authorization: Bearer __CRON_SECRET__" "https://__API_HOST__/api/v1/import-export/cron/sync-google-sheet-product-catalog"'

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Không tìm thấy ${ENV_FILE}"
  exit 1
fi

append_env_if_missing() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    echo "  đã có: ${key}"
  else
    echo "${key}=${value}" >>"$ENV_FILE"
    echo "  + thêm: ${key}"
  fi
}

echo "==> Thêm cấu hình GOOGLE_SHEETS_PRODUCT_CATALOG_* vào backend/.env"
if ! grep -q '^# Đồng bộ sản phẩm — 41 cột Excel' "$ENV_FILE" 2>/dev/null; then
  {
    echo ""
    echo "# Đồng bộ sản phẩm — 41 cột Excel → Google Sheet catalog (cron 3:30 sáng VN)"
  } >>"$ENV_FILE"
fi
append_env_if_missing "GOOGLE_SHEETS_PRODUCT_CATALOG_SYNC_ENABLED" "true"
append_env_if_missing "GOOGLE_SHEETS_PRODUCT_CATALOG_SPREADSHEET_ID" "1iRaVEHjRupYRiB6sVv87m43EaZlR_I1laCuCL77CzRw"
append_env_if_missing "GOOGLE_SHEETS_PRODUCT_CATALOG_SHEET_GID" "1079257836"

CRON_SECRET="$(grep -m1 '^CRON_SECRET=' "$ENV_FILE" | cut -d= -f2- | tr -d '\r' || true)"
if [[ -z "$CRON_SECRET" ]]; then
  echo "Cảnh báo: chưa có CRON_SECRET trong .env — bỏ qua cài crontab."
else
  echo "==> Cài cron 3:30 sáng (Asia/Ho_Chi_Minh)"
  JOB="${CRON_LINE/__CRON_SECRET__/$CRON_SECRET}"
  JOB="${JOB/__API_HOST__/$API_HOST}"
  if crontab -l 2>/dev/null | grep -q 'sync-google-sheet-product-catalog'; then
    echo "  crontab đã có dòng sync-google-sheet-product-catalog"
  else
    (crontab -l 2>/dev/null || true; echo "$JOB") | crontab -
    echo "  + đã thêm crontab"
  fi
  crontab -l | grep sync-google-sheet-product-catalog || true
fi

echo "==> Restart API"
pm2 restart "${PM2_API_NAME:-188-api}" 2>/dev/null || echo "  (bỏ qua pm2 — chạy thủ công: pm2 restart 188-api)"

echo ""
echo "Kiểm tra env:"
grep -E '^GOOGLE_SHEETS_PRODUCT_CATALOG_' "$ENV_FILE" || true
echo ""
echo "Chạy thử ngay (tuỳ chọn, ~3–5 phút):"
echo "  SECRET=\$(grep '^CRON_SECRET=' backend/.env | cut -d= -f2-)"
echo "  curl -sS -m 3600 -H \"Authorization: Bearer \$SECRET\" \"https://${API_HOST}/api/v1/import-export/cron/sync-google-sheet-product-catalog\""
echo ""
echo "Xong."
