#!/usr/bin/env bash
# Dọn job bản địa hóa ảnh kẹt trên VPS.
# Usage:
#   cd /var/www/188.com.vn && bash deploy/cancel-image-localization-job.sh --nuke 7cc916e4e5b241519ed681b3a46a8f23
#   bash deploy/cancel-image-localization-job.sh --nuke --all-active
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
VENV="${BACKEND}/.venv"

echo "==> Dừng API (bắt buộc — worker ghi đè DB nếu API còn chạy)"
pm2 stop 188-api 2>/dev/null || true
sleep 4

# Giết worker/subprocess còn sót (orphan sau pm2 stop)
pkill -9 -f "imgloc-" 2>/dev/null || true
pkill -9 -f "_multiprocess_job_entry" 2>/dev/null || true
pkill -9 -f "image_localization_job" 2>/dev/null || true
sleep 1

echo "==> Dọn DB + reset SP processing"
cd "${BACKEND}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"

ARGS=()
NUKE=0
ALL=0
JOB_ID=""
for arg in "$@"; do
  case "$arg" in
    --nuke) NUKE=1; ARGS+=("--nuke") ;;
    --all-active) ALL=1; ARGS+=("--all-active") ;;
    --delete) ARGS+=("--delete") ;;
    *) JOB_ID="$arg" ;;
  esac
done

if [[ $NUKE -eq 0 ]]; then
  ARGS+=("--delete")
  NUKE=1
fi

if [[ -n "${JOB_ID}" ]]; then
  python scripts/cancel_image_localization_job.py "${JOB_ID}" "${ARGS[@]}"
elif [[ $ALL -eq 1 ]]; then
  python scripts/cancel_image_localization_job.py --all-active "${ARGS[@]}"
else
  python scripts/cancel_image_localization_job.py "${ARGS[@]}"
fi
deactivate

echo "==> Khởi động lại API (tắt resume 1 lần để tránh chạy lại job cũ)"
cd "${ROOT}"
IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP=false pm2 start 188-api --update-env 2>/dev/null \
  || IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP=false pm2 restart 188-api --update-env
pm2 save || true

echo ""
echo "✅ Xong. Trên trình duyệt: F12 → Console → dán:"
echo "localStorage.removeItem('admin:products:image_localization_jobs');localStorage.removeItem('admin:products:image_localization_job');location.reload();"
