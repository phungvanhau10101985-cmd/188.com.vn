#!/usr/bin/env bash
# Chạy trên VPS: sudo bash /var/www/188.com.vn/deploy/patch-nginx-188-on-vps.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chạy: sudo bash $0"
  exit 1
fi

SITE=/etc/nginx/sites-enabled/188.com.vn
ENABLED=/etc/nginx/sites-enabled

echo "=== 1) File trong sites-enabled (bỏ .bak khỏi thư mục này) ==="
ls -la "$ENABLED"

echo ""
echo "=== 2) File nào khai báo server_name 188.com.vn ==="
grep -l 'server_name 188.com.vn' "$ENABLED"/* 2>/dev/null || true

# File .bak trong sites-enabled vẫn được nginx load → trùng server_name
for bak in "$ENABLED"/*.bak* "$ENABLED"/*~; do
  [[ -e "$bak" ]] || continue
  echo "Di chuyển backup ra khỏi sites-enabled: $bak"
  mkdir -p /etc/nginx/backups-188
  mv "$bak" /etc/nginx/backups-188/
done

if [[ ! -f "$SITE" ]]; then
  echo "Không thấy $SITE"
  exit 1
fi

cp -a "$SITE" "/etc/nginx/backups-188/188.com.vn.$(date +%Y%m%d_%H%M%S)"

echo ""
echo "=== 3) Sửa timeout 180s -> 900s trong $SITE ==="
sed -i 's/proxy_send_timeout 180s;/proxy_send_timeout 900s;/g' "$SITE"
sed -i 's/proxy_read_timeout 180s;/proxy_read_timeout 900s;/g' "$SITE"

echo ""
echo "=== 4) Thêm location export nếu thiếu ==="
if ! grep -q 'location /api/v1/import-export/export/' "$SITE"; then
  python3 <<'PY'
from pathlib import Path

site = Path("/etc/nginx/sites-enabled/188.com.vn")
text = site.read_text(encoding="utf-8")
needle = "    location /api/v1/import-export/import/ {"
block = """    location /api/v1/import-export/export/ {
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

"""
if needle not in text:
    raise SystemExit("Không tìm thấy block import trong config — sửa tay bằng nano.")
if "location /api/v1/import-export/export/" in text:
    print("Đã có block export, bỏ qua.")
else:
    site.write_text(text.replace(needle, block + needle, 1), encoding="utf-8")
    print("Đã chèn block export.")
PY
else
  echo "Đã có block export."
fi

echo ""
echo "=== 5) Kiểm tra và reload ==="
nginx -t
systemctl reload nginx

echo ""
echo "=== 6) Kết quả (chỉ file 188.com.vn) ==="
grep -E 'import-export/export|location /api/|proxy_read_timeout|proxy_send_timeout' "$SITE" || true
