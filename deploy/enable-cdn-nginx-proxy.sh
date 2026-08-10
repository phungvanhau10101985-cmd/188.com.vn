#!/usr/bin/env bash
# Bat proxy anh Bunny CDN qua domain chinh 188.com.vn â€” khac phuc anh khong tai duoc tren
# mang di dong (vd. Viettel 5G) chan dai IP chia se cua Bunny. Domain rieng cdn.188.com.vn
# van CNAME toi cung IP Bunny (156.146.56.161 / 2400:52e0:1500::979:1) nen doi domain khong
# giup duoc â€” phai cho anh "di muon" domain/IP cua chinh 188.com.vn (chac chan khong bi chan).
#
# Chay tren VPS (repo tai /var/www/188.com.vn):
#   cd /var/www/188.com.vn
#   sudo bash deploy/enable-cdn-nginx-proxy.sh
#
# Idempotent â€” chay lai nhieu lan an toan (tu bo qua neu block /cdn-media/ da co).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chay: sudo bash $0"
  exit 1
fi

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
SITE="${NGINX_SITE_FILE:-/etc/nginx/sites-enabled/188.com.vn}"
BACKEND_ENV="${ROOT}/backend/.env"
FRONTEND_ENV="${ROOT}/frontend/.env.local"
NEW_CDN_BASE="${CDN_PROXY_BASE:-https://188.com.vn/cdn-media}"
BUNNY_ORIGIN="${BUNNY_ORIGIN_HOST:-188comvn.b-cdn.net}"

echo "=== 1) Kiem tra file nginx site ==="
if [[ ! -f "$SITE" ]]; then
  echo "Khong thay $SITE â€” dat NGINX_SITE_FILE=... neu ten khac (xem: ls /etc/nginx/sites-enabled)."
  exit 1
fi
mkdir -p /etc/nginx/backups-188
cp -a "$SITE" "/etc/nginx/backups-188/188.com.vn.$(date +%Y%m%d_%H%M%S).before-cdn-proxy"
echo "Da backup: /etc/nginx/backups-188/"

echo ""
echo "=== 2) Them location /cdn-media/ (proxy toi Bunny) neu chua co ==="
if grep -q 'location /cdn-media/' "$SITE"; then
  echo "Da co block /cdn-media/, bo qua."
else
  SITE_PATH="$SITE" BUNNY_ORIGIN="$BUNNY_ORIGIN" python3 <<'PY'
import os
from pathlib import Path

site_path = Path(os.environ["SITE_PATH"])
bunny_origin = os.environ["BUNNY_ORIGIN"]
text = site_path.read_text(encoding="utf-8")

needle = "    location / {"
if needle not in text:
    raise SystemExit(f"Khong tim thay '{needle}' trong {site_path} â€” chen tay bang nano.")

block = f"""    # Proxy anh Bunny qua cung domain 188.com.vn - ISP chan *.b-cdn.net van xem duoc.
    location /cdn-media/ {{
        proxy_pass https://{bunny_origin}/;
        proxy_ssl_server_name on;
        proxy_set_header Host {bunny_origin};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_http_version 1.1;
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        proxy_cache_valid 200 7d;
        add_header X-CDN-Proxy "188.com.vn" always;
    }}

"""
site_path.write_text(text.replace(needle, block + needle, 1), encoding="utf-8")
print("Da chen block /cdn-media/.")
PY
fi

echo ""
echo "=== 3) Kiem tra cu phap + reload nginx ==="
nginx -t
systemctl reload nginx
echo "OK â€” nginx da reload."

upsert() {
  local key="$1" val="$2" file="$3"
  if [[ ! -f "$file" ]]; then
    echo "Khong thay $file â€” bo qua $key (tao file .env truoc neu can)."
    return
  fi
  cp -a "$file" "${file}.bak-$(date +%Y%m%d-%H%M%S)"
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}=.*|${key}=${val}|" "$file"
    echo "-> updated ${key}=${val} (${file})"
  else
    printf '\n# CDN proxy qua %s (fix anh khong tai duoc tren mang di dong chan Bunny)\n%s=%s\n' "$NEW_CDN_BASE" "$key" "$val" >> "$file"
    echo "+  added   ${key}=${val} (${file})"
  fi
}

echo ""
echo "=== 4) Cap nhat backend/.env: BUNNY_CDN_PUBLIC_BASE ==="
upsert BUNNY_CDN_PUBLIC_BASE "$NEW_CDN_BASE" "$BACKEND_ENV"

echo ""
echo "=== 5) Cap nhat frontend/.env.local: NEXT_PUBLIC_CDN_URL ==="
upsert NEXT_PUBLIC_CDN_URL "$NEW_CDN_BASE" "$FRONTEND_ENV"

echo ""
echo "=== XONG phan nginx + .env â€” con 2 buoc BAT BUOC (NEXT_PUBLIC_* chi ap dung sau khi build lai) ==="
cat <<EOF
1) Restart API doc BUNNY_CDN_PUBLIC_BASE moi:
     pm2 restart 188-api --update-env && pm2 save

2) Rebuild + restart frontend de NEXT_PUBLIC_CDN_URL moi co hieu luc:
     cd "$ROOT"
     DEPLOY_SKIP_GIT=1 DEPLOY_STOP_PM2_BEFORE_BUILD=1 DEPLOY_SKIP_LINT=1 NODE_BUILD_HEAP_MB=3072 bash ./deploy/update-vps.sh main

3) Kiem tra: mo 1 URL anh san pham, domain phai la 188.com.vn/cdn-media/... :
     curl -I "https://188.com.vn/cdn-media/logo%20head%20188.png"
   (nen tra 200, header X-CDN-Proxy: 188.com.vn)
EOF
