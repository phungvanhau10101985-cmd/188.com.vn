import re

from _load_tra_cuu_js import load_tra_cuu_js

js = load_tra_cuu_js()
# find module that exports i.d
for pat in [r'i\.d="[^"]+"', r'i\.d=t\.env[^;]+', r'\.d="https://api[^"]+"', r'TrackAndTraceItemCode\?[^"]+']:
    hits = re.findall(pat, js)
    if hits:
        print("PAT", pat, hits[:5])

# search TrackAndTraceItemCode callers
idx = 0
n = 0
while n < 10:
    pos = js.find("TrackAndTraceItemCode", idx)
    if pos == -1:
        break
    n += 1
    print("occurrence", n, js[pos : pos + 300])
    idx = pos + 1

# find what i.d equals - search for export d:
for needle in ['d="https://api.myems.vn', 'd=i', 'return{d:', '.d=r']:
    pos = js.find(needle)
    if pos != -1:
        print("needle", needle, js[pos-80:pos+120])
