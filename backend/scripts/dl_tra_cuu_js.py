import re
import requests
import urllib3
from pathlib import Path

urllib3.disable_warnings()

OUT = Path(__file__).resolve().parent / "tra-cuu.js"
# File này nằm trong .gitignore — tải local khi cần phân tích, không commit (có thể chứa API key bên thứ ba).

js = requests.get(
    "https://ems.com.vn/_next/static/chunks/pages/tra-cuu/tra-cuu-buu-gui-ef94b0567c4d2397b095.js",
    timeout=20,
).text
OUT.write_text(js, encoding="utf-8")
print("saved", OUT, "len", len(js))
for pat in [
    r"https?://[^\"']+",
    r"/api/[a-zA-Z0-9_./-]+",
    r"tra-cuu[^\"']*",
    r"tracking[^\"']*",
]:
    hits = sorted(set(re.findall(pat, js)))
    if hits:
        print("PATTERN", pat)
        for h in hits[:30]:
            print(" ", h)
