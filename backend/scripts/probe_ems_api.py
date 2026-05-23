"""Temporary probe script for EMS tracking APIs."""
from __future__ import annotations

import json
import re
import urllib3

import requests

urllib3.disable_warnings()

TOKEN = "d3196f828f8a9ef0f689b0aa9e80023d"
CODE = "EH042737692VN"


def main() -> None:
    session = requests.Session()
    session.verify = False

    login = session.get("https://bill.ems.com.vn/login", timeout=20)
    print("login", login.status_code, "cookies", list(session.cookies.keys()))
    csrf = None
    m = re.search(r'name="csrf-token" content="([^"]+)"', login.text)
    if m:
        csrf = m.group(1)
        print("csrf", csrf[:24])

    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf

    payloads = [
        {"tracking_code": CODE},
        {"code": CODE},
        {"tracking_codes": CODE},
        {"tracking_code": CODE, "merchant_token": TOKEN},
    ]
    for payload in payloads:
        resp = session.post(
            "https://bill.ems.com.vn/api/tracking",
            json=payload,
            headers=headers,
            timeout=20,
        )
        print("POST api/tracking", payload, "=>", resp.status_code)
        try:
            data = resp.json()
            print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        except Exception:
            print(resp.text[:4000])

    # Laravel XSRF from cookie
    from urllib.parse import unquote

    xsrf = unquote(session.cookies.get("XSRF-TOKEN", ""))
    xsrf_headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-XSRF-TOKEN": xsrf,
        "Referer": "https://bill.ems.com.vn/login",
    }
    resp = session.post(
        "https://bill.ems.com.vn/api/tracking",
        json={"tracking_code": CODE},
        headers=xsrf_headers,
        timeout=20,
    )
    print("POST api/tracking xsrf =>", resp.status_code)
    try:
        data = resp.json()
        print(json.dumps(data, ensure_ascii=False, indent=2)[:6000])
    except Exception:
        print(resp.text[:6000])

    # ws.ems.com.vn variants
    for base in ("http://ws.ems.com.vn", "https://api.my.ems.com.vn"):
        url = f"{base}/api/v1/orders/tracking/{CODE}"
        try:
            resp = requests.get(
                url,
                params={"merchant_token": TOKEN},
                timeout=20,
                verify=False,
                headers={"Accept": "application/json"},
            )
            print("GET", url, "=>", resp.status_code, resp.text[:800])
        except Exception as exc:
            print("GET", url, "ERR", exc)

    # MyEMS docs paths
    myems_paths = [
        f"/shipments/{CODE}",
        f"/shipments/tracking/{CODE}",
        f"/shipments/{CODE}/tracking",
        f"/api/v1/shipments/{CODE}",
        f"/api/v1/shipments/tracking/{CODE}",
    ]
    for path in myems_paths:
        url = "https://api.my.ems.com.vn" + path
        try:
            resp = requests.get(
                url,
                params={"merchant_token": TOKEN},
                timeout=20,
                verify=False,
                headers={"Accept": "application/json"},
            )
            if resp.text.strip().startswith("{"):
                print("GET", url, "=>", resp.status_code, resp.text[:800])
        except Exception as exc:
            print("GET", url, "ERR", type(exc).__name__)

    # Public EMS track - inspect page source for API
    for url in (
        "https://ems.com.vn/tra-cuu/tra-cuu-buu-gui",
        f"https://bill.ems.com.vn/orders/search?tracking_code={CODE}",
        f"https://bill.ems.com.vn/orders?tracking_code={CODE}",
    ):
        try:
            resp = session.get(url, timeout=20)
            text = resp.text
            print("GET", url, resp.status_code, "len", len(text))
            if CODE in text or "phát thành công" in text.lower():
                print("  contains tracking data hints")
            for pat in re.findall(r"/api/[a-zA-Z0-9/_-]+", text):
                if "tracking" in pat or "tra-cuu" in pat or "order" in pat:
                    print("  route", pat)
        except Exception as exc:
            print("GET", url, "ERR", type(exc).__name__)


if __name__ == "__main__":
    main()
