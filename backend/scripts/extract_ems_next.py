import json
import re

html = open("scripts/ems_public_page_snip.html", encoding="utf-8").read()
m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html)
if m:
    data = json.loads(m.group(1))
    open("scripts/ems_next_data.json", "w", encoding="utf-8").write(
        json.dumps(data, ensure_ascii=False, indent=2)
    )
    print("saved next data", len(m.group(1)))
else:
    print("no next data")
    for pat in ["api", "tracking", "tra-cuu", "graphql", "fetch("]:
        if pat in html.lower():
            print("contains", pat)

# extract script src from page
srcs = re.findall(r'src="([^"]+\.js[^"]*)"', html)
print("js count", len(srcs))
for s in srcs[:20]:
    print(s)
