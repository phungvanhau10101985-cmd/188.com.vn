#!/usr/bin/env bash
# Đồng bộ timeout nginx cho 188.com.vn (export Excel, API chậm, Next proxy).
# Chạy trên VPS: sudo bash deploy/apply-nginx-188-timeouts.sh
set -euo pipefail

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
  echo "Không tìm thấy file nginx 188.com.vn. Thử:"
  printf '  %s\n' "${SITE_CANDIDATES[@]}"
  echo "Hoặc copy deploy/nginx-site-188.com.vn.conf.example thủ công."
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chạy với sudo: sudo bash $0"
  exit 1
fi

BACKUP="${SITE_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
cp -a "$SITE_FILE" "$BACKUP"
echo "Backup: $BACKUP"

FULL_EXAMPLE="$(cd "$(dirname "$0")" && pwd)/nginx-site-188.com.vn.conf.example"
if [[ -f "$FULL_EXAMPLE" ]] && grep -q 'server_name 188.com.vn;' "$FULL_EXAMPLE"; then
  echo "Ghi đè bằng mẫu đầy đủ: $FULL_EXAMPLE -> $SITE_FILE"
  cp -a "$FULL_EXAMPLE" "$SITE_FILE"
else
  echo "Không có mẫu đầy đủ — patch tối thiểu trên $SITE_FILE"
  sed -i 's/proxy_send_timeout 180s;/proxy_send_timeout 900s;/g' "$SITE_FILE"
  sed -i 's/proxy_read_timeout 180s;/proxy_read_timeout 900s;/g' "$SITE_FILE"

  if ! grep -q 'location /api/v1/import-export/export/' "$SITE_FILE"; then
    EXPORT_BLOCK=$(cat <<'NGINX'

    # Export Excel toàn catalog (~30k SP) — 3–15 phút trên VPS
    location /api/v1/import-export/export/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 75s;
        proxy_send_timeout 900s;
        proxy_read_timeout 900s;
    }
NGINX
)
    # Chèn trước block import nếu có, không thì trước location /api/
    if grep -q 'location /api/v1/import-export/import/' "$SITE_FILE"; then
      perl -0777 -i -pe "s|\\n    location /api/v1/import-export/import/|\\n${EXPORT_BLOCK}\\n    location /api/v1/import-export/import/|s" "$SITE_FILE"
    else
      perl -0777 -i -pe "s|\\n    location /api/ \\{|${EXPORT_BLOCK}\\n    location /api/ \\{|s" "$SITE_FILE"
    fi
  fi

  if grep -q 'location / {' "$SITE_FILE" && ! grep -A20 'location / {' "$SITE_FILE" | grep -q 'proxy_read_timeout'; then
    sed -i '/location \/ {/,/proxy_buffering off;/ {
      /proxy_set_header Connection "upgrade";/a\
        proxy_connect_timeout 75s;\
        proxy_send_timeout 900s;\
        proxy_read_timeout 900s;
    }' "$SITE_FILE" 2>/dev/null || true
  fi
fi

nginx -t
systemctl reload nginx

echo ""
echo "Đã reload nginx. Kiểm tra:"
nginx -T 2>/dev/null | grep -E 'server_name 188|location /api/v1/import-export|location /api/|location / {|proxy_read_timeout|proxy_send_timeout' | head -40
