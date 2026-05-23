import re
import requests
import urllib3

urllib3.disable_warnings()
s = requests.Session()
s.verify = False
for path in ["/js/app.js", "/js/custom.js"]:
    js = s.get("https://bill.ems.com.vn" + path, timeout=20).text
    open("scripts" + path.replace("/", "_"), "w", encoding="utf-8").write(js)
    routes = sorted(set(re.findall(r'["\'](/[^"\']+)["\']', js)))
    print("FILE", path, "routes", len(routes))
    for r in routes:
        low = r.lower()
        if any(x in low for x in ("api", "order", "track", "tra", "ship", "detail")):
            print(" ", r)
