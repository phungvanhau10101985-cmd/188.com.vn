#!/usr/bin/env bash
# Thêm /health/db và /health/storefront vào nginx 188.com.vn (monitor UptimeRobot).
# Chạy trên VPS: sudo bash deploy/patch-nginx-health-routes.sh
set -euo pipefail

SITE="${NGINX_SITE_FILE:-/etc/nginx/sites-enabled/188.com.vn}"
if [[ ! -f "$SITE" ]]; then
  echo "Không thấy $SITE"
  exit 1
fi

if grep -q 'location = /health/storefront' "$SITE"; then
  echo "Đã có /health/storefront — bỏ qua."
  exit 0
fi

cp -a "$SITE" "${SITE}.bak.$(date +%Y%m%d_%H%M%S)"

python3 - "$SITE" <<'PY'
import re
import sys
from pathlib import Path

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")
block = """
    location = /health/db {
        proxy_pass http://127.0.0.1:8001/health/db;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
    }

    location = /health/storefront {
        proxy_pass http://127.0.0.1:8001/health/storefront;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
    }
"""
needle = "location = /health {"
if needle not in text:
    raise SystemExit("Không tìm thấy location = /health { — sửa tay theo deploy/nginx-site-188.com.vn.conf.example")
m = re.search(
    r"(location = /health \{.*?\n    \})\n",
    text,
    flags=re.DOTALL,
)
if not m:
    raise SystemExit("Không parse được block /health")
text = text[: m.end()] + block + text[m.end() :]
site.write_text(text, encoding="utf-8")
print("Đã thêm /health/db và /health/storefront")
PY

nginx -t
systemctl reload nginx
echo "OK — thử: curl -s -o /dev/null -w '%{http_code}\n' https://188.com.vn/health/storefront"
