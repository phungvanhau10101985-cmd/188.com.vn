"""Scan bill.ems.com.vn JS bundles for tracking routes."""
from __future__ import annotations

import re

import requests
import urllib3

urllib3.disable_warnings()

TOKEN = "d3196f828f8a9ef0f689b0aa9e80023d"
CODE = "EH042737692VN"


def main() -> None:
    session = requests.Session()
    session.verify = False
    login = session.get("https://bill.ems.com.vn/login", timeout=20)
    js_urls = re.findall(r'src="([^"]+\.js[^"]*)"', login.text)
    for src in js_urls:
        url = src if src.startswith("http") else f"https://bill.ems.com.vn/{src.lstrip('/')}"
        if "google" in url or "recaptcha" in url:
            continue
        try:
            js = session.get(url, timeout=15).text
        except Exception:
            continue
        routes = sorted(
            {
                m
                for m in re.findall(r'["\'](/[^"\']+)["\']', js)
                if any(x in m.lower() for x in ("track", "tra", "order", "ship", "api"))
            }
        )
        if routes:
            print("JS", url)
            for route in routes[:40]:
                print(" ", route)

    # Try merchant token as header on ws + bill
    headers = {
        "Accept": "application/json",
        "merchant_token": TOKEN,
        "Authorization": f"Bearer {TOKEN}",
        "X-Merchant-Token": TOKEN,
    }
    urls = [
        f"http://ws.ems.com.vn/api/v1/orders/tracking/{CODE}",
        f"http://ws.ems.com.vn/api/v2/orders/tracking/{CODE}",
        f"https://bill.ems.com.vn/ws/api/v1/orders/tracking/{CODE}",
        f"https://bill.ems.com.vn/api/v1/orders/tracking/{CODE}",
    ]
    for url in urls:
        try:
            resp = session.get(url, params={"merchant_token": TOKEN}, headers=headers, timeout=20)
            print("GET", url, resp.status_code, resp.text[:300])
        except Exception as exc:
            print("GET", url, type(exc).__name__)


if __name__ == "__main__":
    main()
