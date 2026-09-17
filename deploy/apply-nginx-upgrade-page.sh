#!/usr/bin/env bash
# Cài trang «hệ thống đang nâng cấp» khi nginx không kết nối được Next/API (deploy / 502).
# Idempotent. Chạy trên VPS: sudo bash deploy/apply-nginx-upgrade-page.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chạy với sudo: sudo bash $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HTML_SRC="${SCRIPT_DIR}/static/upgrade.html"
SNIPPET_SRC="${SCRIPT_DIR}/nginx-snippet-upgrade-page.conf"
HTML_DST="/var/www/html/188-upgrade.html"
SNIPPET_DST="/etc/nginx/snippets/188-upgrade-page.conf"
INCLUDE_LINE='    include /etc/nginx/snippets/188-upgrade-page.conf;'

if [[ ! -f "$HTML_SRC" ]]; then
  echo "Thiếu $HTML_SRC"
  exit 1
fi
if [[ ! -f "$SNIPPET_SRC" ]]; then
  echo "Thiếu $SNIPPET_SRC"
  exit 1
fi

mkdir -p /var/www/html /etc/nginx/snippets /etc/nginx/backups-188
cp -a "$HTML_SRC" "$HTML_DST"
chmod 644 "$HTML_DST"
cp -a "$SNIPPET_SRC" "$SNIPPET_DST"
chmod 644 "$SNIPPET_DST"
echo "Đã ghi $HTML_DST và $SNIPPET_DST"

python3 - "$INCLUDE_LINE" <<'PY'
import sys
from pathlib import Path

include_line = sys.argv[1]
marker = "188-upgrade-page.conf"
candidates = []
enabled = Path("/etc/nginx/sites-enabled")
if enabled.is_dir():
    for p in sorted(enabled.iterdir()):
        if p.is_file() or p.is_symlink():
            candidates.append(p.resolve() if p.is_symlink() else p)

seen = set()
files = []
for p in candidates:
    rp = str(p)
    if rp in seen:
        continue
    seen.add(rp)
    if p.name.startswith("nanoai"):
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        continue
    if "proxy_pass" not in text:
        continue
    files.append(p)

changed = 0
for path in files:
    original = path.read_text(encoding="utf-8")
    if marker in original:
        print(f"Đã có include: {path}")
        continue
    lines = original.splitlines(keepends=True)
    out = []
    i = 0
    inserted_in_file = False
    while i < len(lines):
        line = lines[i]
        out.append(line)
        stripped = line.strip()
        if stripped.startswith("server {") or stripped == "server {":
            # Chèn sau dòng server { (và các dòng listen/server_name ngay sau nếu muốn: chèn ngay)
            # Tránh server chỉ redirect: chỉ chèn nếu block có proxy_pass.
            depth = line.count("{") - line.count("}")
            block = [line]
            j = i + 1
            while j < len(lines) and depth > 0:
                block.append(lines[j])
                depth += lines[j].count("{") - lines[j].count("}")
                j += 1
            block_text = "".join(block)
            if "proxy_pass" in block_text and marker not in block_text:
                out.append(include_line + "\n")
                inserted_in_file = True
        i += 1
    if not inserted_in_file:
        print(f"Bỏ qua (không chèn được): {path}")
        continue
    bak = Path("/etc/nginx/backups-188") / f"{path.name}.{path.stat().st_mtime_ns}.bak"
    bak.write_text(original, encoding="utf-8")
    path.write_text("".join(out), encoding="utf-8")
    print(f"Đã chèn include: {path} (backup {bak.name})")
    changed += 1

print(f"Đã cập nhật {changed} file nginx.")
PY

echo "==> nginx -t"
nginx -t
systemctl reload nginx
echo "OK: 502/503/504 sẽ hiện trang nâng cấp (503) thay vì Bad Gateway mặc định."
