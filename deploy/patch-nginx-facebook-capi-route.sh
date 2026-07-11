#!/usr/bin/env bash
set -euo pipefail

# Chèn location = /api/facebook-capi vào site nginx 188.com.vn (idempotent).
# Chạy trên VPS:
#   sudo bash deploy/patch-nginx-facebook-capi-route.sh

SITE="${NGINX_SITE_FILE:-/etc/nginx/sites-enabled/188.com.vn}"

if [[ ! -f "$SITE" ]]; then
  echo "Khong tim thay file nginx: $SITE"
  echo "Dat NGINX_SITE_FILE neu duong dan khac."
  exit 1
fi

if rg -n "location\s*=\s*/api/facebook-capi" "$SITE" >/dev/null 2>&1; then
  echo "Da co block /api/facebook-capi trong $SITE"
  nginx -t
  systemctl reload nginx
  echo "OK: nginx da reload"
  exit 0
fi

BACKUP="/etc/nginx/backups-188"
mkdir -p "$BACKUP"
cp -a "$SITE" "$BACKUP/188.com.vn.$(date +%Y%m%d_%H%M%S)"

python3 - "$SITE" <<'PY'
from pathlib import Path
import re
import sys

site = Path(sys.argv[1])
text = site.read_text(encoding="utf-8")

block = r"""
    # Meta CAPI route cua Next.js (tranh roi vao FastAPI /api/)
    # PHAI dat truoc location /api/
    location = /api/facebook-capi {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
"""

anchor = re.search(r"^\s*location\s+/api/\s*\{", text, flags=re.M)
if not anchor:
    raise SystemExit("Khong tim thay block 'location /api/ {' de chen truoc.")

pos = anchor.start()
new_text = text[:pos] + block + "\n" + text[pos:]
site.write_text(new_text, encoding="utf-8")
print("Inserted /api/facebook-capi block before /api/.")
PY

nginx -t
systemctl reload nginx
echo "OK: da chen block /api/facebook-capi va reload nginx"
