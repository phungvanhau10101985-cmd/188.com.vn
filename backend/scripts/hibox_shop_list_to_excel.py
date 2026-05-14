"""
Danh sách SP trên trang shop Hi-box (Nuxt SPA), ví dụ https://hibox.mn/shop/140074342

Playwright: cuộn + lăn chuột cho lazy-load (không cookie trừ khi truyền --cookies).

  cd backend && set PYTHONPATH=. && python scripts/hibox_shop_list_to_excel.py ^
    --url "https://hibox.mn/shop/140074342" --wheel-burst 40 --out runtime/hibox_shop.xlsx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

_extract_js = """
() => {
  const rows = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll('a[href*="/v/"]'));
  for (const a of anchors) {
    let href = (a.href || '').split('#')[0];
    if (!/hibox\\.mn\\/v\\//i.test(href)) continue;
    const m = href.match(/\\/v\\/([^/?#]+)/i);
    if (!m) continue;
    const slug = m[1];
    if (seen.has(slug)) continue;
    seen.add(slug);
    const title = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 480);
    rows.push({ slug, title, url: href });
  }
  return rows;
}
"""

_SCROLL_HEIGHT_JS = "() => Math.max(document.documentElement.scrollHeight||0,document.body.scrollHeight||0)"


def _norm_cookie(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from urllib.parse import urlparse

    if not isinstance(c, dict):
        return None
    name = str(c.get("name") or "").strip()
    if not name:
        return None
    val = c.get("value")
    if val is None:
        return None
    domain = str(c.get("domain") or ".hibox.mn").strip() or ".hibox.mn"
    if domain.startswith("http"):
        domain = urlparse(domain).hostname or ".hibox.mn"
    out: Dict[str, Any] = {"name": name, "value": str(val), "domain": domain, "path": str(c.get("path") or "/")}
    if c.get("expirationDate"):
        try:
            out["expires"] = int(float(c["expirationDate"]))
        except (TypeError, ValueError):
            pass
    if isinstance(c.get("httpOnly"), bool):
        out["httpOnly"] = c["httpOnly"]
    if isinstance(c.get("secure"), bool):
        out["secure"] = c["secure"]
    ss = c.get("sameSite")
    if ss == "no_restriction":
        out["sameSite"] = "None"
    return out


def _load_optional_cookies(path: Optional[Path]) -> List[Dict[str, Any]]:
    if not path or not path.is_file():
        return []
    data = json.loads(path.read_text("utf-8").strip())
    arr = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(arr, list):
        raise SystemExit("Cookie file phải là JSON array hoặc có key cookies")
    out: List[Dict[str, Any]] = []
    for c in arr:
        nc = _norm_cookie(c) if isinstance(c, dict) else None
        if nc:
            out.append(nc)
    return out


_slug_re = re.compile(r'hibox\.mn/v/([^"?#\s>]+)', re.I)


def _harvest_urls_from_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for m in _slug_re.finditer(text):
        slug = m.group(1).rstrip("'\"/")
        if not slug:
            continue
        url = f"https://hibox.mn/v/{slug}"
        rows.append({"slug": slug, "title": "", "url": url})
    return rows


def _make_response_hook(bucket: List[Dict[str, Any]]) -> Any:
    allow = frozenset({"xhr", "fetch", "document"})

    def on_resp(resp: Any) -> None:
        try:
            if resp.request.resource_type not in allow:
                return
            b = resp.body()
            if len(b) > 3_000_000:
                return
            t = b.decode("utf-8", errors="ignore")
        except Exception:
            return
        if "/v/" not in t and "hibox" not in t.lower():
            return
        bucket.extend(_harvest_urls_from_text(t))

    return on_resp


def _unique_slugs(rows: List[Dict[str, Any]]) -> set[str]:
    return {str(r.get("slug") or "").strip() for r in rows if str(r.get("slug") or "").strip()}


def scrape_shop(
    page: Any,
    url: str,
    *,
    wait_ms: int,
    scroll_pause_ms: int,
    max_scroll_passes: int,
    stable_idle_passes: int,
    stable_min_delta_px: int,
    wheel_burst: int,
    net_bucket: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    net_bucket.clear()
    page.goto(url, wait_until="domcontentloaded", timeout=180_000)
    page.wait_for_timeout(max(0, wait_ms))

    collected: List[Dict[str, Any]] = []
    idle = 0
    prev_h: Optional[float] = None

    for _ in range(max(1, max_scroll_passes)):
        n_before = len(_unique_slugs(collected))
        bw = max(1, wheel_burst)
        hw = max(80, scroll_pause_ms // 2)
        for _w in range(bw):
            page.mouse.wheel(0, 2800)
            page.wait_for_timeout(hw)
        page.evaluate(
            "window.scrollTo(0, Math.max(document.documentElement.scrollHeight,document.body.scrollHeight))"
        )
        page.wait_for_timeout(scroll_pause_ms)

        rows = page.evaluate(_extract_js)
        if isinstance(rows, list):
            collected.extend(dict(r) for r in rows if isinstance(r, dict))
        collected.extend(net_bucket[:])
        net_bucket.clear()

        cur_h = float(page.evaluate(_SCROLL_HEIGHT_JS))
        growth = stable_min_delta_px + 1 if prev_h is None else (cur_h - prev_h)
        prev_h = cur_h

        n_after = len(_unique_slugs(collected))
        no_new_slugs = n_after == n_before

        if growth < stable_min_delta_px and no_new_slugs:
            idle += 1
            if idle >= stable_idle_passes:
                break
        else:
            idle = 0

    html = page.content()
    collected.extend(_harvest_urls_from_text(html))
    collected.extend(net_bucket[:])
    net_bucket.clear()

    # dedupe by slug, merge title/url
    by: Dict[str, Dict[str, Any]] = {}
    for r in collected:
        slug = str(r.get("slug") or "").strip()
        if not slug:
            continue
        u = str(r.get("url") or f"https://hibox.mn/v/{slug}").strip()
        t = str(r.get("title") or "").strip()
        if slug not in by:
            by[slug] = {"slug": slug, "title": t, "url": u}
        else:
            o = by[slug]
            if len(t) > len(str(o.get("title") or "")):
                o["title"] = t
            if u and len(u) >= len(str(o.get("url") or "")):
                o["url"] = u
    return list(by.values())


def main() -> None:
    ap = argparse.ArgumentParser(description="Hi-box shop listing → Excel (Playwright)")
    ap.add_argument("--url", default="https://hibox.mn/shop/140074342")
    ap.add_argument("--out", type=Path, default=Path("hibox_shop_list.xlsx"))
    ap.add_argument("--cookies", type=Path, default=None, help="JSON cookie tùy chọn (Chrome export)")
    ap.add_argument("--wait-ms", type=int, default=4000)
    ap.add_argument("--scroll-pause-ms", type=int, default=700)
    ap.add_argument("--max-scroll-passes", type=int, default=260)
    ap.add_argument("--stable-idle-passes", type=int, default=14)
    ap.add_argument("--stable-min-delta", type=int, default=42)
    ap.add_argument("--wheel-burst", type=int, default=40)
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium")

    ck = _load_optional_cookies(args.cookies)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.new_page()
        net: List[Dict[str, Any]] = []
        page.on("response", _make_response_hook(net))

        if ck:
            page.goto("https://hibox.mn/", wait_until="domcontentloaded", timeout=120_000)
            ctx.add_cookies(ck)

        rows = scrape_shop(
            page,
            args.url.strip(),
            wait_ms=args.wait_ms,
            scroll_pause_ms=args.scroll_pause_ms,
            max_scroll_passes=args.max_scroll_passes,
            stable_idle_passes=args.stable_idle_passes,
            stable_min_delta_px=args.stable_min_delta,
            wheel_burst=args.wheel_burst,
            net_bucket=net,
        )
        browser.close()

    if not rows:
        raise SystemExit(
            "0 sản phẩm. Thử tắt --headless, kiểm tra URL (404/500), hoặc thêm --cookies."
        )

    df = pd.DataFrame(rows)[["slug", "title", "url"]]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(args.out, index=False, engine="openpyxl")
    print(f"Wrote {len(df)} rows → {args.out.resolve()}")


if __name__ == "__main__":
    main()
