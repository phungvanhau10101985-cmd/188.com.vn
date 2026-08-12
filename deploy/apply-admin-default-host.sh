#!/usr/bin/env bash
# Redirect /admin trên apex → admin.188.com.vn + CORS admin + deploy proxy.ts
set -euo pipefail

SITE=/etc/nginx/sites-enabled/188.com.vn
ENVF=/var/www/188.com.vn/backend/.env
ROOT=/var/www/188.com.vn

if [[ ! -f "$SITE" ]]; then
  echo "missing $SITE" >&2
  exit 1
fi

# Chèn redirect /admin trước location / (chỉ trong server 188.com.vn)
if grep -q 'location ^~ /admin' "$SITE"; then
  echo "nginx /admin redirect already present"
else
  python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/188.com.vn")
text = p.read_text(encoding="utf-8")
needle = "    location / {\n        proxy_pass http://127.0.0.1:3001;"
block = """    # Admin mặc định qua subdomain DNS-only (bypass Cloudflare ~100s timeout)
    location ^~ /admin {
        return 308 https://admin.188.com.vn$request_uri;
    }

    location / {
        proxy_pass http://127.0.0.1:3001;"""
# Chỉ thay trong server_name 188.com.vn (file có 1 khối location / chính)
if needle not in text:
    raise SystemExit("needle location / not found")
# replace last occurrence (main server block) — file only has one matching pattern for :3001 under /
count = text.count(needle)
if count < 1:
    raise SystemExit("no match")
text = text.replace(needle, block, 1)
p.write_text(text, encoding="utf-8")
print("inserted /admin → admin.188.com.vn redirect")
PY
fi

# CORS
if grep -qE '^[[:space:]]*BACKEND_CORS_ORIGINS=' "$ENVF"; then
  if grep -q 'admin.188.com.vn' "$ENVF"; then
    echo "CORS already has admin.188.com.vn"
  else
    sed -i -E 's|^([[:space:]]*BACKEND_CORS_ORIGINS=)(.*)|\1\2,https://admin.188.com.vn|' "$ENVF"
    # clean duplicate commas
    sed -i -E 's/,,+/,/g' "$ENVF"
    echo "added https://admin.188.com.vn to BACKEND_CORS_ORIGINS"
  fi
else
  echo "BACKEND_CORS_ORIGINS=https://188.com.vn,https://www.188.com.vn,https://admin.188.com.vn" >> "$ENVF"
fi

# frontend env
FE_ENV="${ROOT}/frontend/.env.local"
if [[ -f "$FE_ENV" ]]; then
  if grep -qE '^[[:space:]]*NEXT_PUBLIC_ADMIN_ORIGIN=' "$FE_ENV"; then
    sed -i -E 's|^[[:space:]]*NEXT_PUBLIC_ADMIN_ORIGIN=.*|NEXT_PUBLIC_ADMIN_ORIGIN=https://admin.188.com.vn|' "$FE_ENV"
  else
    printf '\nNEXT_PUBLIC_ADMIN_ORIGIN=https://admin.188.com.vn\n' >> "$FE_ENV"
  fi
fi

nginx -t
systemctl reload nginx

# Restart API để nạp CORS
pm2 restart 188-api --update-env || true

echo "==== verify redirect ===="
curl -sS -o /dev/null -w "apex_admin:%{http_code} -> %{redirect_url}\n" --max-redirs 0 https://188.com.vn/admin/products/source-stock-check || true
curl -sS -o /dev/null -w "admin_host:%{http_code}\n" https://admin.188.com.vn/admin/products/source-stock-check
curl -sS -o /dev/null -w "admin_root:%{http_code} -> %{redirect_url}\n" --max-redirs 0 https://admin.188.com.vn/ || true
echo DONE
