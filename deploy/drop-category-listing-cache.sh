#!/usr/bin/env bash
# Xóa bảng category_listing_cache (cache danh mục bản 09/06 — không dùng ở fe5ece1).
#
#   cd /var/www/188.com.vn && bash deploy/drop-category-listing-cache.sh
#   cd /var/www/188.com.vn && bash deploy/drop-category-listing-cache.sh --dry-run
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${ROOT}/backend"
VENV="${BACKEND}/.venv"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

if [[ ! -d "$VENV" ]]; then
  echo "❌ Không thấy ${VENV}"
  exit 1
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"
cd "${BACKEND}"
export DROP_CACHE_DRY="${DRY}"

PYTHONPATH=. python - <<'PY'
import os
import sys

dry = os.environ.get("DROP_CACHE_DRY", "0") == "1"

from sqlalchemy import inspect, text
from app.db.session import engine

table = "category_listing_cache"
names = set(inspect(engine).get_table_names())
print(f"DATABASE: {engine.url.render_as_string(hide_password=True)}")
print(f"Bảng {table}: {'có' if table in names else 'không tồn tại'}")

if table not in names:
    sys.exit(0)

try:
    with engine.connect() as conn:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
    print(f"Số dòng cache: {n}")
except Exception as exc:
    print(f"(Không đếm được row: {exc})")

if dry:
    print("--dry-run: bỏ qua DROP TABLE.")
    sys.exit(0)

with engine.begin() as conn:
    conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
print(f"✅ Đã xóa bảng {table}.")
PY
