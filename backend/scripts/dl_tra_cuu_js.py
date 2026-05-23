import re
import requests
import urllib3

urllib3.disable_warnings()

js = requests.get(
    "https://ems.com.vn/_next/static/chunks/pages/tra-cuu/tra-cuu-buu-gui-ef94b0567c4d2397b095.js",
    timeout=20,
).text
open("scripts/tra-cuu.js", "w", encoding="utf-8").write(js)
print("len", len(js))
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
