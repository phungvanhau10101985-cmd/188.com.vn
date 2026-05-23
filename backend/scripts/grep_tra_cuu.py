import re

js = open("scripts/tra-cuu.js", encoding="utf-8").read()
for needle in ["api.myems.vn", "myems.vn", "tracking", "shipments", "merchant_token", "tra-cuu"]:
    idx = 0
    found = 0
    while True:
        pos = js.find(needle, idx)
        if pos == -1:
            break
        found += 1
        snippet = js[max(0, pos - 80) : pos + 120]
        if found <= 8:
            print("---", needle, found, "---")
            print(snippet.replace("\n", " "))
        idx = pos + len(needle)
    print("total", needle, found)
