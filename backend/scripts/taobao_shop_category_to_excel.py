"""
Quét danh sách sản phẩm trên trang category cửa hàng Taobao (shop*.taobao.com) bằng Playwright + cookie đăng nhập, xuất Excel.

Cookie: export JSON … Không commit …

`--google-search-mode serp` (mặc định): mở trang Google tìm kiếm rồi điều hướng shop với referer=SERP (`synthetic`: referer google.com/url; `none`: không set).

  cd backend && set PYTHONPATH=. && python scripts/taobao_shop_category_to_excel.py ^
    --cookies G:\\path\\taobao_cookies.json ^
    --url "https://shop140074342.taobao.com/category.htm" ^
    --google-search-mode serp ^
    --out taobao_shop_items.xlsx

Mặc định chạy có cửa sổ (--headed) vì một số trang Alibaba/Taobao phản hồi khác với headless.

Lưu ý: tuân thủ điều khoản Taobao; cookie là thông tin đăng nhập — giữ kín và làm mới nếu đã lộ.

Giới hạn số SP: **không có một con số cố định** — phụ thuộc shop (tổng SP đăng bán), layout trang,
API của Taobao. Shop **chỉ load khi cuộn** (không nút «xem thêm»): script cuộn lặp đến khi chiều cao trang
và số SP mới không đổi (`--stable-idle-passes`), có trần `--max-scroll-passes`. Tuỳ chọn `--more-rounds`
cho shop vẫn có nút «加载更多».
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _normalize_playwright_cookie(cookie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(cookie, dict):
        return None
    name = str(cookie.get("name") or "").strip()
    if not name:
        return None
    value = cookie.get("value")
    if value is None:
        return None
    value = str(value)

    domain = str(cookie.get("domain") or ".taobao.com").strip() or ".taobao.com"
    if domain.startswith("http://") or domain.startswith("https://"):
        try:
            domain = urlparse(domain).hostname or ".taobao.com"
        except Exception:
            domain = ".taobao.com"
    path = str(cookie.get("path") or "/").strip() or "/"

    out: Dict[str, Any] = {"name": name, "value": value, "domain": domain, "path": path}

    exp = cookie.get("expires")
    if exp is None and cookie.get("expirationDate") is not None:
        try:
            exp = int(float(cookie["expirationDate"]))
        except (TypeError, ValueError):
            exp = None
    if exp is not None:
        try:
            out["expires"] = int(exp)
        except (TypeError, ValueError):
            pass

    if isinstance(cookie.get("httpOnly"), bool):
        out["httpOnly"] = cookie["httpOnly"]
    if isinstance(cookie.get("secure"), bool):
        out["secure"] = cookie["secure"]

    ss = cookie.get("sameSite")
    if isinstance(ss, str) and ss.strip():
        sm = ss.strip().lower()
        mp = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
            "unspecified": "Lax",
            "no_restriction": "None",
        }
        if sm in mp:
            out["sameSite"] = mp[sm]

    return out


def _load_cookies(path: Path) -> List[Dict[str, Any]]:
    raw = path.read_text(encoding="utf-8").strip()
    data = json.loads(raw)
    cookies = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(cookies, list):
        raise SystemExit("File cookie phải là JSON array hoặc object có key «cookies».")
    out: List[Dict[str, Any]] = []
    for c in cookies:
        nc = _normalize_playwright_cookie(c) if isinstance(c, dict) else None
        if nc:
            out.append(nc)
    return out


_EXTRACT_JS = r"""
() => {
  const seen = new Set();
  const rows = [];

  function cleanTitle(s) {
    s = (s || '').replace(/\s+/g, ' ').trim();
    if (s.length > 500) s = s.slice(0, 500);
    return s;
  }

  function looksEncryptedPrice(t) {
    t = (t || '').trim();
    return /^\[[^\]]+#/.test(t) || (/^\[[^\]]+\]$/.test(t) && !/\d/.test(t));
  }

  /** Giá hiển thị dạng ¥174.67 — bỏ khoảng trắng lạ (NBSP), lấy số thập phân. */
  function extractPriceFromPriceBlock(pc) {
    if (!pc) return '';
    const full = (pc.innerText || pc.textContent || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ');
    let m = full.match(/[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,2})?)\b/);
    if (m) return m[1].replace(/,/g, '').trim();

    const nodes = pc.querySelectorAll(
      '[class*="text-price"], span.text-price, [class*="price--"], [class*="Price--"], em, strong, b, span, div'
    );
    for (const el of nodes) {
      const raw = (el.textContent || '').trim().replace(/\u00a0/g, ' ');
      if (!raw || looksEncryptedPrice(raw)) continue;
      if (/人付款|万|^\d+\+?$/.test(raw) && raw.length < 14) continue;
      let m2 = raw.match(/^[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,2})?)$/);
      if (m2) return m2[1].replace(/,/g, '').trim();
      m2 = raw.match(/^([\d]{1,7}(?:[.,]\d{1,2})?)\s*(?:元起|元)?$/);
      if (m2 && m2[1]) return m2[1].replace(/,/g, '').trim();
    }
    const priRoot = pc.querySelector('[class*="price--"], [class*="Price--"]');
    if (priRoot) {
      const t = (priRoot.innerText || '').replace(/\u00a0/g, ' ');
      const m3 = t.match(/[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,2})?)/);
      if (m3) return m3[1].replace(/,/g, '').trim();
    }
    return '';
  }

  function extractTitleFromDesc(dc) {
    if (!dc) return '';
    const direct =
      dc.querySelector(':scope > [class*="title--"]') ||
      dc.querySelector(':scope > [class*="Title--"]');
    const candidates = [];
    if (direct) candidates.push(direct);
    dc.querySelectorAll('[class*="title--"], [class*="Title--"], [class*="itemTitle"]').forEach((el) => {
      if (!candidates.includes(el)) candidates.push(el);
    });
    let best = '';
    for (const el of candidates) {
      let t = cleanTitle(el.innerText || el.textContent || '');
      if (t.includes('¥') || t.includes('￥') || /人付款/.test(t)) continue;
      if (t.length > best.length) best = t;
    }
    return best;
  }

  /** Một ô card shop (skin 2025: cardContainer + descContainer anh/em với ảnh). */
  function extractFromDescContainer(dc) {
    let title = extractTitleFromDesc(dc);
    let price = '';
    const pc = dc.querySelector('[class*="priceContainer"]');
    if (pc) price = extractPriceFromPriceBlock(pc);
    return { title, price };
  }

  function findCardRoot(a) {
    const byCard = a.closest('[class*="cardContainer--"]');
    if (byCard && byCard.querySelector('[class*="descContainer"]')) return byCard;
    let el = a;
    for (let i = 0; i < 18 && el; i++) {
      try {
        if (el.querySelector && el.querySelector('[class*="descContainer"]')) return el;
      } catch (e) {}
      el = el.parentElement;
    }
    return a.closest('li') || a.parentElement;
  }

  function pickProductImageFromCard(card) {
    if (!card) return '';
    const main = card.querySelector('[class*="mainImage--"] img, [class*="mainImage"] img');
    if (main) {
      let s =
        main.src ||
        main.getAttribute('data-src') ||
        main.getAttribute('data-ks-lazyload') ||
        '';
      if (s && !s.includes('O1CN01CYtPWu1MUBqQAUK9D')) return s;
    }
    let img = '';
    for (const im of card.querySelectorAll(
      'img[src*="alicdn"], img[data-src*="alicdn"], img[src*="gw.alicdn"], img[src*="imgextra"]'
    )) {
      const s =
        im.src || im.getAttribute('data-src') || im.getAttribute('data-ks-lazyload') || '';
      if (!s) continue;
      if (s.includes('atmosphere_center_image')) continue;
      if (im.closest('[class*="title--"], [class*="Title--"]')) continue;
      if (s.includes('O1CN01CYtPWu1MUBqQAUK9D')) continue;
      img = s;
      break;
    }
    return img || '';
  }

  function pushRow(id, href, title, price, img) {
    if (seen.has(id)) return;
    seen.add(id);
    title = cleanTitle(title);
    if (title.length > 240) title = title.slice(0, 240);
    rows.push({
      item_id: id,
      title,
      url: href,
      price_text: price,
      image_url: img || '',
    });
  }

  /** Ưu tiên: cardContainer (tiêu đề + giá không nằm trong cùng nhánh <a> với link). */
  const cards = document.querySelectorAll('[class*="cardContainer--"]');
  for (const card of cards) {
    const a = card.querySelector(
      'a[href*="item.htm"], a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="tmall.com/item"]'
    );
    if (!a) continue;
    const href = (a.href || '').split('#')[0];
    const m = href.match(/[?&]id=(\d+)/);
    if (!m) continue;
    const id = m[1];
    const dc = card.querySelector('[class*="descContainer"]');
    let title = '';
    let price = '';
    if (dc) {
      const ex = extractFromDescContainer(dc);
      title = ex.title;
      price = ex.price;
    }
    if (!title || title.length < 4) {
      title = cleanTitle(a.innerText || a.textContent || '');
    }
    let img = pickProductImageFromCard(card);
    if (!price) {
      let scope = card;
      for (let i = 0; i < 14 && scope; i++) {
        const txt = (scope.innerText || '').replace(/\u00a0/g, ' ');
        const pm = txt.match(/[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,2})?)/);
        if (pm) {
          price = pm[1].replace(/,/g, '').trim();
          break;
        }
        scope = scope.parentElement;
      }
    }
    pushRow(id, href, title, price, img);
  }

  const anchors = Array.from(document.querySelectorAll(
    'a[href*="item.htm"], a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="tmall.com/item"]'
  ));

  for (const a of anchors) {
    let href = (a.href || '').split('#')[0];
    const m = href.match(/[?&]id=(\d+)/);
    if (!m) continue;
    const id = m[1];
    if (seen.has(id)) continue;

    const root = findCardRoot(a);
    const dc = root && root.querySelector ? root.querySelector('[class*="descContainer"]') : null;
    let title = '';
    let price = '';
    if (dc) {
      const ex = extractFromDescContainer(dc);
      title = ex.title;
      price = ex.price;
    }
    if (!title || title.length < 4) {
      title = cleanTitle(a.innerText || a.textContent || '');
    }
    let img = pickProductImageFromCard(root || a.parentElement);
    if (!img) {
      let card = (root || a).closest('[class*="cardContainer--"]');
      img = pickProductImageFromCard(card || root || a.parentElement);
    }
    if (!price) {
      let scope = a.closest('[class*="cardContainer--"], div');
      for (let i = 0; i < 14 && scope; i++) {
        const txt = (scope.innerText || '').replace(/\u00a0/g, ' ');
        const pm = txt.match(/[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,2})?)/);
        if (pm) {
          price = pm[1].replace(/,/g, '').trim();
          break;
        }
        scope = scope.parentElement;
      }
    }
    pushRow(id, href, title, price, img);
  }
  return rows;
}
"""

_URL_ITEM_TB = re.compile(r"(?:https?:)?//item\.taobao\.com/item\.htm\?[^\s\"'<>]+", re.I)
_URL_ITEM_TMALL = re.compile(r"(?:https?:)?//detail\.tmall\.com/item\.htm\?[^\s\"'<>]+", re.I)


def _urls_with_scheme(raw: str) -> str:
    u = raw.strip().rstrip("\\,.);")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        return "https://" + u[len("http://") :]
    return u


def _merge_item_rows(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Gộp hai bản ghi cùng item_id: title ưu tiên chuỗi dài hơn; giá/ảnh ưu tiên có nội dung."""
    ta, tb = str(a.get("title") or "").strip(), str(b.get("title") or "").strip()
    title = ta if len(ta) >= len(tb) else tb
    pa, pb = str(a.get("price_text") or "").strip(), str(b.get("price_text") or "").strip()
    price_text = pb if pb else pa
    ia, ib = str(a.get("image_url") or "").strip(), str(b.get("image_url") or "").strip()
    image_url = ib if ib else ia
    url = str(a.get("url") or b.get("url") or "").strip()
    iid = str(a.get("item_id") or b.get("item_id") or "").strip()
    return {
        "item_id": iid,
        "title": title,
        "price_text": price_text,
        "url": url,
        "image_url": image_url,
    }


def _harvest_item_urls_from_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rx in (_URL_ITEM_TB, _URL_ITEM_TMALL):
        for m in rx.finditer(text):
            u = _urls_with_scheme(m.group(0))
            im = re.search(r"[?&]id=(\d+)", u)
            if not im:
                continue
            rows.append({"item_id": im.group(1), "title": "", "url": u, "price_text": "", "image_url": ""})
    return rows


def _fallback_shop_urls(primary: str) -> List[str]:
    """Trang shop đôi khi chỉ có đủ dữ liệu trên search.htm hoặc host *.world.taobao.com."""
    pu = urlparse(primary.strip())
    scheme = pu.scheme or "https"
    host = pu.hostname or ""
    query = pu.query
    qsuffix = f"?{query}" if query else ""
    base_path = (pu.path or "/").rstrip("/") or "/"
    seen: set[str] = set()
    out: List[str] = []

    def add(full: str) -> None:
        if full not in seen:
            seen.add(full)
            out.append(full)

    path_queries: List[str] = []
    if base_path != "/":
        path_queries.append((base_path + (f"?{query}" if query else "")))
    path_queries.append("/search.htm")

    hosts = [host]
    if host.endswith(".taobao.com") and ".world.taobao.com" not in host:
        hosts.append(host.replace(".taobao.com", ".world.taobao.com"))
    elif host.endswith(".world.taobao.com"):
        hosts.append(host.replace(".world.taobao.com", ".taobao.com"))

    for h in hosts:
        if not h:
            continue
        for pq in path_queries:
            add(f"{scheme}://{h}{pq}")

    return out


# Nhãn nút «xem thêm» hay gặp trên shop Taobao PC (Ice/Ant Design).
_MORE_UI_LABELS = (
    "加载更多",
    "查看更多",
    "更多宝贝",
    "展开更多",
    "点击加载",
    "查看全部",
)


def _try_click_load_more(page: Any, *, settle_ms: int = 1400) -> bool:
    """Bấm một nút/link «xem thêm» trong khối nội dung shop nếu có. Trả về True nếu đã click."""
    containers = (
        "#ice-container",
        "[class*='contentContainer']",
        "[class*='content--']",
        "body",
    )
    for csel in containers:
        scope = page.locator(csel).first
        try:
            if scope.count() == 0:
                continue
        except Exception:
            continue
        for label in _MORE_UI_LABELS:
            for tag in ("button", "a", "div", "span"):
                loc = scope.locator(f'{tag}:has-text("{label}")').first
                try:
                    if loc.count() == 0:
                        continue
                    if not loc.is_visible(timeout=500):
                        continue
                    loc.scroll_into_view_if_needed(timeout=2500)
                    page.wait_for_timeout(200)
                    loc.click(timeout=4000)
                    page.wait_for_timeout(settle_ms)
                    return True
                except Exception:
                    continue
        for cls_frag in ("loadMore", "LoadMore", "load-more"):
            loc = scope.locator(
                f'button[class*="{cls_frag}"], a[class*="{cls_frag}"], '
                f'div[class*="{cls_frag}"], span[class*="{cls_frag}"]'
            ).first
            try:
                if loc.count() == 0:
                    continue
                if not loc.is_visible(timeout=500):
                    continue
                loc.scroll_into_view_if_needed(timeout=2500)
                loc.click(timeout=4000)
                page.wait_for_timeout(settle_ms)
                return True
            except Exception:
                continue
    return False


def _unique_item_ids(rows: List[Dict[str, Any]]) -> set[str]:
    return {str(r.get("item_id") or "").strip() for r in rows if str(r.get("item_id") or "").strip()}


_SCROLL_HEIGHT_JS = (
    "() => Math.max(document.documentElement.scrollHeight||0, document.body.scrollHeight||0)"
)


def _visit_and_collect(
    page: Any,
    target_url: str,
    *,
    scroll_pause_ms: int,
    wait_ms: int,
    net_bucket: List[Dict[str, Any]],
    more_rounds: int,
    max_products: int,
    max_scroll_passes: int,
    stable_idle_passes: int,
    stable_min_delta_px: int,
    wheel_burst: int,
    referer: Optional[str] = None,
) -> List[Dict[str, Any]]:
    net_bucket.clear()
    nav: Dict[str, Any] = {"wait_until": "domcontentloaded", "timeout": 120_000}
    if referer:
        nav["referer"] = referer
    page.goto(target_url, **nav)
    page.wait_for_timeout(max(0, wait_ms))

    collected: List[Dict[str, Any]] = []
    waves = max(0, more_rounds) + 1

    for wave in range(waves):
        if wave > 0:
            if not _try_click_load_more(page):
                break

        idle = 0
        prev_h: Optional[float] = None

        for _pass in range(max(1, max_scroll_passes)):
            n_before = len(_unique_item_ids(collected))

            burst = max(1, wheel_burst)
            half_wait = max(80, scroll_pause_ms // 2)
            for _ in range(burst):
                page.mouse.wheel(0, 2800)
                page.wait_for_timeout(half_wait)
            page.evaluate(
                "window.scrollTo(0, Math.max(document.documentElement.scrollHeight,"
                " document.body.scrollHeight))"
            )
            page.wait_for_timeout(scroll_pause_ms)

            rows = page.evaluate(_EXTRACT_JS)
            if isinstance(rows, list):
                collected.extend(r for r in rows if isinstance(r, dict))
            collected.extend(net_bucket[:])
            net_bucket.clear()

            cur_h = float(page.evaluate(_SCROLL_HEIGHT_JS))
            growth = stable_min_delta_px + 1 if prev_h is None else (cur_h - prev_h)
            prev_h = cur_h

            n_after = len(_unique_item_ids(collected))
            no_new = n_after == n_before

            if growth < stable_min_delta_px and no_new:
                idle += 1
                if idle >= stable_idle_passes:
                    break
            else:
                idle = 0

            if max_products > 0 and n_after >= max_products:
                break

        html = page.content()
        collected.extend(_harvest_item_urls_from_text(html))
        collected.extend(net_bucket[:])
        net_bucket.clear()

        if max_products > 0 and len(_unique_item_ids(collected)) >= max_products:
            break

    return collected


def _make_response_handler(bucket: List[Dict[str, Any]]):
    _ALLOW_RT = frozenset({"xhr", "fetch", "document"})

    def on_response(resp: Any) -> None:
        try:
            if resp.request.resource_type not in _ALLOW_RT:
                return
            body = resp.body()
            if len(body) > 3_500_000:
                return
            text = body.decode("utf-8", errors="ignore")
        except Exception:
            return
        if (
            "item.taobao" not in text
            and "detail.tmall.com" not in text
            and "item.htm" not in text
            and "auctionId" not in text
            and "itemId" not in text
        ):
            return
        bucket.extend(_harvest_item_urls_from_text(text))

    return on_response


def main() -> None:
    ap = argparse.ArgumentParser(description="Taobao shop category → Excel (Playwright + cookies)")
    ap.add_argument("--cookies", required=True, type=Path, help="JSON cookies (Chrome export)")
    ap.add_argument(
        "--url",
        default="https://shop140074342.taobao.com/category.htm",
        help="URL trang category cửa hàng",
    )
    ap.add_argument(
        "--google-search-mode",
        choices=("serp", "synthetic", "none"),
        default="serp",
        help="serp=Mở Google Search rồi vào shop (referer=SERP); synthetic=referer google.com/url ; none=bỏ.",
    )
    ap.add_argument("--out", type=Path, default=Path("taobao_shop_category.xlsx"))
    ap.add_argument(
        "--max-scroll-passes",
        type=int,
        default=280,
        help="Trần số vòng cuộn (mỗi vòng = wheel burst + scrollTo đáy); tăng nếu shop dài.",
    )
    ap.add_argument(
        "--stable-idle-passes",
        type=int,
        default=14,
        help="Dừng khi đủ nhiều vòng liên tiếp không tăng chiều cao đáng kể và không có SP mới.",
    )
    ap.add_argument(
        "--stable-min-delta",
        type=int,
        default=42,
        help="Px coi là «không tăng chiều cao» khi scrollHeight_new - scrollHeight_old < delta.",
    )
    ap.add_argument(
        "--wheel-burst",
        type=int,
        default=6,
        help="Số lần mouse.wheel mỗi vòng cuộn (lazy-load hay kích hoạt khi cuộn).",
    )
    ap.add_argument("--scroll-pause-ms", type=int, default=700)
    ap.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt (có thể bị chặn)")
    ap.add_argument("--wait-ms", type=int, default=5000, help="Chờ sau load trước khi cuộn")
    ap.add_argument(
        "--more-rounds",
        type=int,
        default=0,
        help="Tuỳ chọn: thử bấm «加载更多» giữa các đợt (shop chỉ cuộn là load — để 0).",
    )
    ap.add_argument(
        "--max-products",
        type=int,
        default=0,
        help="Dừng sớm trong một lần mở URL khi đã đủ số SP khác nhau (0 = không giới hạn).",
    )
    args = ap.parse_args()

    if not args.cookies.is_file():
        raise SystemExit(f"Không thấy file cookie: {args.cookies}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Cài Playwright: pip install playwright && playwright install chromium")

    cookies = _load_cookies(args.cookies)
    url = (args.url or "").strip()
    if not url.startswith("http"):
        raise SystemExit("--url phải là http(s) URL")

    all_rows: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        net_bucket: List[Dict[str, Any]] = []
        page.on("response", _make_response_handler(net_bucket))

        seed = "https://www.taobao.com/"
        page.goto(seed, wait_until="domcontentloaded", timeout=120_000)
        context.add_cookies(cookies)

        google_ref: Optional[str] = None
        if args.google_search_mode == "synthetic":
            google_ref = (
                "https://www.google.com/url?sa=t&source=web&rct=j&url="
                + quote(url.strip().split("#")[0], safe="")
            )
        elif args.google_search_mode == "serp":
            try:
                host = urlparse(url).hostname or "shop.taobao.com"
                q = quote(f"{host} category taobao shop")
                page.goto(
                    f"https://www.google.com/search?q={q}&hl=zh-CN&igu=1",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                page.wait_for_timeout(1400)
                google_ref = page.url
            except Exception:
                google_ref = (
                    "https://www.google.com/url?sa=t&source=web&rct=j&url="
                    + quote(url.strip().split("#")[0], safe="")
                )

        for cand in _fallback_shop_urls(url):
            chunk = _visit_and_collect(
                page,
                cand,
                scroll_pause_ms=args.scroll_pause_ms,
                wait_ms=args.wait_ms,
                net_bucket=net_bucket,
                more_rounds=args.more_rounds,
                max_products=args.max_products,
                max_scroll_passes=args.max_scroll_passes,
                stable_idle_passes=args.stable_idle_passes,
                stable_min_delta_px=args.stable_min_delta,
                wheel_burst=args.wheel_burst,
                referer=google_ref,
            )
            all_rows.extend(chunk)

        browser.close()

    # Deduplicate theo item_id, gộp trường từ DOM + từ API/HTML
    by_id: Dict[str, Dict[str, Any]] = {}
    for r in all_rows:
        iid = str(r.get("item_id") or "").strip()
        if not iid:
            continue
        if iid not in by_id:
            by_id[iid] = dict(r)
        else:
            by_id[iid] = _merge_item_rows(by_id[iid], r)

    final_list = list(by_id.values())
    if not final_list:
        raise SystemExit(
            "Không trích được sản phẩm (0 dòng). Thử không --headless, tăng --max-scroll-passes, "
            "hoặc kiểm tra cookie / xác minh trình duyệt."
        )

    df = pd.DataFrame(final_list)
    cols = ["item_id", "title", "price_text", "url", "image_url"]
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(args.out, index=False, engine="openpyxl")
    print(f"Wrote {len(df)} rows → {args.out.resolve()}")


if __name__ == "__main__":
    main()
