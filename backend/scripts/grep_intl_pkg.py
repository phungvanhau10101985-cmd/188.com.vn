import re

js = open("scripts/tra-cuu.js", encoding="utf-8").read()
for needle in ["internationalpackage", "queryString", "TrackAndTraceItemCode", "List_TBL_DELIVERY", "TBL_INFO", "MA_E1"]:
    idx = 0
    n = 0
    while n < 8:
        pos = js.find(needle, idx)
        if pos == -1:
            break
        n += 1
        print("---", needle, n, "---")
        print(js[pos - 150 : pos + 250].replace("\n", " "))
        idx = pos + len(needle)
