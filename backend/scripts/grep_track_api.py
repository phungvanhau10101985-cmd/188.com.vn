import re

js = open("scripts/tra-cuu.js", encoding="utf-8").read()
for needle in ["TrackAndTraceItemCode", "EmsDosmetic", "EmsDomestic", "TrackAndTrace", "i.d,", "EMS_API_URL"]:
    idx = 0
    n = 0
    while n < 5:
        pos = js.find(needle, idx)
        if pos == -1:
            break
        n += 1
        print("---", needle, n, "---")
        print(js[pos - 120 : pos + 220].replace("\n", " "))
        idx = pos + len(needle)
