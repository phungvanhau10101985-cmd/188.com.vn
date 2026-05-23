import requests
import urllib3

urllib3.disable_warnings()

TOKEN = "d3196f828f8a9ef0f689b0aa9e80023d"
CODE = "EH042737692VN"
BASE = "https://bill.ems.com.vn"

paths = [
    "/api/merchant/tracking",
    "/api/merchant/orders/tracking",
    "/api/merchant/orders/detail",
    "/api/external/tracking",
    "/api/public/tracking",
    "/api/order/tracking",
    "/api/orders/tracking",
    "/api/orders/trace",
    "/api/orders/detail",
    "/api/orders/search",
    "/merchant/api/tracking",
    "/merchant/api/v1/tracking",
    "/ws/api/v1/orders/tracking/{code}",
    "/api/v1/orders/tracking/{code}",
    "/api/v1/merchant/orders/tracking/{code}",
    "/orders/detail/{code}",
]

session = requests.Session()
session.verify = False

for path in paths:
    url = BASE + path.replace("{code}", CODE)
    for as_query in (True, False):
        kwargs = {
            "timeout": 15,
            "headers": {"Accept": "application/json"},
        }
        if as_query:
            kwargs["params"] = {"merchant_token": TOKEN, "tracking_code": CODE}
        else:
            kwargs["headers"]["merchant_token"] = TOKEN
            kwargs["headers"]["Authorization"] = f"Bearer {TOKEN}"
        try:
            resp = session.get(url, **kwargs)
        except Exception as exc:
            print("ERR", url, exc)
            continue
        body = resp.text.strip()
        if body.startswith("{") or body.startswith("["):
            print("JSON", url, "q=", as_query, resp.status_code, body[:500])
        elif CODE in body and ("Trạng thái" in body or "phát thành công" in body):
            print("HTML_HIT", url, resp.status_code, len(body))
