import json
import requests
import urllib3

urllib3.disable_warnings()

TOKEN = "d3196f828f8a9ef0f689b0aa9e80023d"
CODE = "EH042737692VN"
BASE = "https://api.myems.vn"

paths = [
    f"/api/v1/orders/tracking/{CODE}",
    f"/shipments/{CODE}",
    f"/shipments/tracking/{CODE}",
    f"/shipments/{CODE}/tracking",
    f"/api/v1/shipments/{CODE}",
    f"/api/v1/shipments/tracking/{CODE}",
    f"/api/tracking/{CODE}",
    f"/api/orders/tracking/{CODE}",
    "/shipments/status",
    "/api/v1/shipments/status",
]

session = requests.Session()
session.verify = False

for path in paths:
    for params in (
        {"merchant_token": TOKEN},
        {"merchant_token": TOKEN, "tracking_code": CODE},
        {"token": TOKEN},
    ):
        url = BASE + path
        try:
            resp = session.get(
                url,
                params=params,
                timeout=20,
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            print("ERR", url, exc)
            continue
        body = resp.text.strip()
        if body.startswith("{") or body.startswith("["):
            print("HIT", url, params, resp.status_code)
            print(body[:2000])
            open("scripts/myems_hit.json", "w", encoding="utf-8").write(body)

# POST variants
posts = [
    ("/api/tracking", {"tracking_code": CODE, "merchant_token": TOKEN}),
    ("/shipments/tracking", {"trackingCode": CODE, "merchant_token": TOKEN}),
    ("/api/v1/shipments/tracking", {"tracking_code": CODE, "merchant_token": TOKEN}),
]
for path, payload in posts:
    try:
        resp = session.post(
            BASE + path,
            json=payload,
            timeout=20,
            headers={"Accept": "application/json"},
        )
        if resp.text.strip().startswith("{"):
            print("POST HIT", path, resp.status_code, resp.text[:2000])
    except Exception as exc:
        print("POST ERR", path, exc)
