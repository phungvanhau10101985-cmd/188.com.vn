#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/admin.188.com.vn")
text = p.read_text(encoding="utf-8")
if "location = / {" in text:
    print("admin root redirect already present")
else:
    needle = "    location / {\n        proxy_pass http://127.0.0.1:3001;"
    insert = (
        "    location = / {\n"
        "        return 302 /admin;\n"
        "    }\n\n"
        "    location / {\n"
        "        proxy_pass http://127.0.0.1:3001;"
    )
    if needle not in text:
        raise SystemExit("needle not found:\n" + text[:1200])
    p.write_text(text.replace(needle, insert), encoding="utf-8")
    print("added location = / -> /admin")
PY
nginx -t
systemctl reload nginx
curl -sS -o /dev/null -w "admin_root:%{http_code} -> %{redirect_url}\n" --max-redirs 0 "https://admin.188.com.vn/" || true
