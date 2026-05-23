import re

js = open("scripts/tra-cuu.js", encoding="utf-8").read()
paths = sorted(set(re.findall(r"/api/[a-zA-Z0-9_./-]+", js)))
for p in paths:
    print(p)

print("\nadmin.ems snippets:")
idx = 0
n = 0
while n < 15:
    pos = js.find("admin.ems.com.vn", idx)
    if pos == -1:
        break
    n += 1
    print(js[pos - 60 : pos + 100].replace("\n", " "))
    idx = pos + 1

print("\nmyems api call snippets:")
for needle in ["EMS_API_URL", "internationalpackage", "getTracking", "gettracking", "TraCuu", "tracuu", "MA_E1", "ItemCode"]:
    pos = js.find(needle)
    if pos != -1:
        print("---", needle, "---")
        print(js[pos - 100 : pos + 200].replace("\n", " "))
