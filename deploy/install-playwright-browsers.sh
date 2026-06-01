#!/usr/bin/env bash
# Tải browser Chromium cho Playwright (import Vipomall, Hibox, 1688, Gemini Web, …).
# Usage (từ root repo):
#   bash deploy/install-playwright-browsers.sh
# Tuỳ chọn: PLAYWRIGHT_WITH_DEPS=1 để cài thêm thư viện hệ thống (cần sudo trên Linux).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
VENV="${BACKEND}/.venv"

if [[ ! -d "${VENV}" ]]; then
  echo "❌ Chưa có ${VENV} — chạy deploy/prepare-vps.sh hoặc pip install -r backend/requirements.txt trước."
  exit 1
fi

# shellcheck disable=SC1090
source "${VENV}/bin/activate"

if ! python -c "import playwright" 2>/dev/null; then
  echo "❌ Package playwright chưa có trong venv. Chạy: pip install -r backend/requirements.txt"
  exit 1
fi

echo "==> Playwright: tải Chromium (headless shell + browser)"
if [[ "${PLAYWRIGHT_WITH_DEPS:-0}" == "1" ]]; then
  python -m playwright install --with-deps chromium
else
  python -m playwright install chromium
fi

echo "✅ Playwright browsers đã sẵn sàng."
deactivate 2>/dev/null || true
