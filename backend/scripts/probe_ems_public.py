"""Probe EMS public + merchant tracking endpoints."""
from __future__ import annotations

import json
import re
from urllib.parse import unquote

import requests
import urllib3

urllib3.disable_warnings()

TOKEN = "d3196f828f8a9ef0f689b0aa9e80023d"
CODE = "EH042737692VN"


def save(name: str, text: str) -> None:
    path = f"scripts/{name}"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("saved", path, "len", len(text))


def main() -> None:
    session = requests.Session()
    session.verify = False

    # Public ems.com.vn page scripts
    page = session.get("https://ems.com.vn/tra-cuu/tra-cuu-buu-gui", timeout=20)
    save("ems_public_page_snip.html", page.text[:120000])
    urls = sorted(set(re.findall(r"https?://[^\"'\s<>]+", page.text)))
    for u in urls:
        low = u.lower()
        if any(x in low for x in ("api", "track", "tracuu", "tra-cuu", "buu", "ems")):
            print("url", u)

    # Try common public APIs
    candidates = [
        ("GET", "https://ems.com.vn/api/tracking", {"code": CODE}),
        ("GET", "https://ems.com.vn/api/tracking", {"tracking_code": CODE}),
        ("POST", "https://ems.com.vn/api/tracking", {"tracking_code": CODE}),
        ("GET", "https://ems.com.vn/api/tra-cuu-buu-gui", {"code": CODE}),
        ("POST", "https://ems.com.vn/api/tra-cuu-buu-gui", {"code": CODE}),
        ("GET", "https://tracking.ems.com.vn/api/tracking", {"code": CODE}),
        ("GET", "https://api.ems.com.vn/tracking", {"code": CODE}),
        ("GET", "https://api.ems.com.vn/v1/tracking", {"trackingCode": CODE}),
        ("GET", f"https://api.ems.com.vn/v1/tracking/{CODE}", {}),
        ("GET", "https://bill.ems.com.vn/api/tracking", {"tracking_code": CODE, "merchant_token": TOKEN}),
        ("GET", "https://bill.ems.com.vn/api/v1/tracking", {"tracking_code": CODE, "merchant_token": TOKEN}),
        ("GET", f"https://bill.ems.com.vn/api/tracking/{CODE}", {"merchant_token": TOKEN}),
        ("GET", f"https://bill.ems.com.vn/api/orders/{CODE}/tracking", {"merchant_token": TOKEN}),
    ]
    for method, url, params in candidates:
        try:
            if method == "GET":
                resp = session.get(
                    url,
                    params=params,
                    timeout=20,
                    headers={"Accept": "application/json, text/plain, */*"},
                )
            else:
                resp = session.post(
                    url,
                    json=params,
                    timeout=20,
                    headers={"Accept": "application/json, text/plain, */*"},
                )
            ct = resp.headers.get("content-type", "")
            body = resp.text
            print(method, url, params, "=>", resp.status_code, ct, "len", len(body))
            if body.strip().startswith("{") or body.strip().startswith("["):
                save(
                    "ems_json_hit.txt",
                    json.dumps({"url": url, "params": params, "body": resp.json()}, ensure_ascii=False, indent=2),
                )
            if CODE in body or "phát thành công" in body.lower() or "chấp nhận gửi" in body.lower():
                save(f"ems_hit_{method.lower()}.html", body)
        except Exception as exc:
            print(method, url, "ERR", type(exc).__name__, exc)


if __name__ == "__main__":
    main()
