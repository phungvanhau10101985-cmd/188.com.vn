#!/usr/bin/env bash
# Áp rate-limit an toàn cho các API nặng DB (PDP by-slug / SEO cluster / user-behavior).
# Chạy trên VPS: sudo bash deploy/apply-nginx-188-rate-limit.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chạy với sudo: sudo bash $0"
  exit 1
fi

SITE_CANDIDATES=(
  /etc/nginx/sites-enabled/188.com.vn
  /etc/nginx/sites-enabled/188-com-vn
  /etc/nginx/sites-available/188.com.vn
  /etc/nginx/sites-available/188-com-vn
)

SITE_FILE=""
for f in "${SITE_CANDIDATES[@]}"; do
  if [[ -f "$f" ]]; then
    SITE_FILE="$f"
    break
  fi
done

if [[ -z "$SITE_FILE" ]]; then
  echo "Không tìm thấy file nginx site 188.com.vn."
  exit 1
fi

BACKUP="${SITE_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
cp -a "$SITE_FILE" "$BACKUP"
echo "Backup site: $BACKUP"

ZONE_FILE="/etc/nginx/conf.d/188-rate-limit.conf"
cat > "$ZONE_FILE" <<'EOF'
# 188.com.vn rate-limit zones (http context)
map $http_cf_connecting_ip $rate_limit_key_188 {
    default $http_cf_connecting_ip;
    "" $binary_remote_addr;
}

limit_req_zone $rate_limit_key_188 zone=api_byslug:20m rate=20r/s;
limit_req_zone $rate_limit_key_188 zone=api_cluster_products:20m rate=10r/s;
limit_req_zone $rate_limit_key_188 zone=api_user_behavior:20m rate=8r/s;
EOF
echo "Wrote: $ZONE_FILE"

SITE_FILE_ENV="$SITE_FILE" python3 <<'PY'
import os
from pathlib import Path

site = Path(os.environ["SITE_FILE_ENV"])
text = site.read_text(encoding="utf-8")
marker = "    # ---- 188 rate-limit guards ----"

if marker in text:
    print("Rate-limit blocks đã tồn tại, bỏ qua chèn.")
else:
    needle = "    location /api/ {"
    block = """    # ---- 188 rate-limit guards ----
    # Cần zones trong /etc/nginx/conf.d/188-rate-limit.conf
    location ~ ^/api/v1/products/by-slug/ {
        limit_req zone=api_byslug burst=40 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location ~ ^/api/v1/seo-clusters/.+/(products|facets)$ {
        limit_req zone=api_cluster_products burst=30 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location ~ ^/api/v1/user-behavior/ {
        limit_req zone=api_user_behavior burst=20 nodelay;
        limit_req_status 429;

        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 15s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    # ---- /188 rate-limit guards ----

"""
    if needle not in text:
        raise SystemExit("Không tìm thấy block `location /api/ {` trong site config.")
    site.write_text(text.replace(needle, block + needle, 1), encoding="utf-8")
    print("Đã chèn rate-limit blocks vào site config.")
PY

nginx -t
systemctl reload nginx
echo "Nginx reloaded."
echo ""
echo "Kiểm tra nhanh:"
nginx -T 2>/dev/null | grep -E '188-rate-limit|limit_req_zone|api_byslug|api_cluster_products|api_user_behavior' | head -40
