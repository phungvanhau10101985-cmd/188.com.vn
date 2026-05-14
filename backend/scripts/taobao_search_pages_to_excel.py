"""
Quét kết quả tìm kiếm Taobao (`s.taobao.com/search?…`) — N trang đầu → Excel.

Đọc **tên shop** (`shopNameText--*`), **giá** (`priceInt--*` ± phần lẻ), tiêu đề / URL / ảnh SP (bỏ icon atmosphere).
Cuộn nhiều vòng `--scroll-rounds` (≈44) để waterfall nạp ~46 ô/trang.

**Mỗi trang SERP Taobao luôn mở qua redirect Google** (`google.com/url?…`) khi không dùng `--google-search-mode none`.
Chi tiết `serp` / `synthetic`, `--google-serp-each-page`, phân trang `url` + `page`/`s`: **`scripts/TAOBAO_SEARCH_GOOGLE_REDIRECT.md`**.
Danh mục mọi script crawl/export khác: **`scripts/CRAWL_DATA_SOURCES.md`**.

Mặc định **`--pages 3`**. **`--pagination-nav url`**: gắn `page` + **`s`**; **`--page-step`** (~48).
**`--pagination-nav click`**: headless hay lỗi → dùng **`url`**. **`--shop-name`** lọc shop.

  python scripts/taobao_search_pages_to_excel.py ^
    --cookies runtime\\taobao_cookies_session.json ^
    --url "https://s.taobao.com/search?page=1&q=WENROO温柔家女鞋&tab=all" ^
    --pages 3 --scroll-rounds 48 ^
    --google-search-mode serp ^
    --out runtime\\taobao_search.xlsx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _normalize_playwright_cookie(cookie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(cookie, dict):
        return None
    name = str(cookie.get("name") or "").strip()
    if not name or cookie.get("value") is None:
        return None
    value = str(cookie.get("value"))
    domain = str(cookie.get("domain") or ".taobao.com").strip() or ".taobao.com"
    if domain.startswith("http://") or domain.startswith("https://"):
        try:
            domain = urlparse(domain).hostname or ".taobao.com"
        except Exception:
            domain = ".taobao.com"
    path = str(cookie.get("path") or "/").strip() or "/"
    out: Dict[str, Any] = {"name": name, "value": value, "domain": domain, "path": path}
    if cookie.get("expirationDate") is not None:
        try:
            out["expires"] = int(float(cookie["expirationDate"]))
        except (TypeError, ValueError):
            pass
    if isinstance(cookie.get("httpOnly"), bool):
        out["httpOnly"] = cookie["httpOnly"]
    if isinstance(cookie.get("secure"), bool):
        out["secure"] = cookie["secure"]
    ss = cookie.get("sameSite")
    if isinstance(ss, str) and ss.strip():
        mp = {"no_restriction": "None", "strict": "Strict", "lax": "Lax"}
        sv = ss.strip().lower()
        if sv in mp:
            out["sameSite"] = mp[sv]
    return out


def _load_cookies(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text("utf-8").strip())
    arr = data.get("cookies") if isinstance(data, dict) else data
    if not isinstance(arr, list):
        raise SystemExit("Cookie JSON: array hoặc {cookies: [...]}")
    out: List[Dict[str, Any]] = []
    for c in arr:
        nc = _normalize_playwright_cookie(c) if isinstance(c, dict) else None
        if nc:
            out.append(nc)
    return out


def _ensure_scheme(url: str) -> str:
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    if not u.startswith("http"):
        return "https://" + u
    return u


def _via_google_redirect_url(destination: str) -> str:
    """Mở SERP TB qua **redirect Google** (`/url?...url=…`) — giống click từ Google, không chỉ header Referer."""
    return (
        "https://www.google.com/url?sa=t&source=web&rct=j&url="
        + quote(_ensure_scheme(destination), safe="")
    )


def _with_search_page(url: str, page: int, *, page_step: int = 48) -> str:
    """TB SERP hay dùng offset **`s`**, chỉ có `page` không đổi ô → mỗi lần vẫn ~1 trang.

    Chuẩn gần đúng: `s=(page-1)*page_step` với `--page-step` (mặc định 48; thử 44–49).
    """
    u = urlparse(_ensure_scheme(url.strip().split("#")[0]))
    pairs = OrderedDict(parse_qsl(u.query, keep_blank_values=True))
    pnum = max(1, int(page))
    step = max(1, int(page_step))
    pairs["page"] = str(pnum)
    pairs["s"] = str(max(0, (pnum - 1) * step))
    q = urlencode(list(pairs.items()))
    scheme = u.scheme or "https"
    return urlunparse((scheme, u.netloc, u.path or "/", u.params, q, ""))


_EXTRACTION_NOTE_JS = r"""
() => {
  const el =
    document.querySelector('[class*="totalPage"], [class*="Page"]') ||
    document.querySelector('.next-pagination');
  const t = document.body.innerText.match(/\b(\d+)\s*\/\s*(\d+)\b/);
  return {
    pagination_guess: t ? `${t[1]}/${t[2]}` : '',
    snippet: ((el && el.innerText) || '').trim().slice(0, 200),
  };
}
"""


_EXTRACT_JS = r"""
() => {
  const seen = new Set();
  const rows = [];

  function cleanTitle(s) {
    s = (s || '').replace(/\s+/g, ' ').trim();
    if (s.length > 500) s = s.slice(0, 480);
    return s;
  }
  function pickPrice(full) {
    const t = (full || '').replace(/\u00a0/g, ' ').replace(/\s+/g, ' ');
    const m = t.match(/[¥￥]\s*([\d]{1,7}(?:[.,]\d{1,4})?)/);
    if (m) return m[1].replace(/,/g, '').trim();
    return '';
  }
  /** Giá skin mới: <div class="priceInt--…">128</div> ± phần thập phân */
  function splitPriceFromDOM(card) {
    if (!card) return '';
    const pi = card.querySelector('[class*="priceInt--"]');
    if (!pi) return '';
    let iTxt = (pi.innerText || pi.textContent || '').replace(/[^\d]/g, '').trim();
    let fTxt = '';
    const wrap =
      pi.closest('[class*="price--"], [class*="Price"], [class*="PriceWrap"]') || pi.parentElement;
    const floats = wrap
      ? wrap.querySelectorAll(
          '[class*="priceFloat--"], [class*="priceDecimal"], [class*="decimal--"], ' +
          '[class*="xiaoshu--"], [class*="PriceFloat"], [class*="minor--"]'
        )
      : [];
    floats.forEach((el) => {
      const t = (el.innerText || '').replace(/[^\d]/g, '').trim();
      if (!fTxt && t && t.length >= 1 && t.length <= 6 && !el.closest('[class*="title"]'))
        fTxt = t.slice(0, 4);
    });
    if (!fTxt && wrap) {
      const sib = pi.nextElementSibling;
      const st = ((sib && sib.innerText) || '').replace(/[^\d.]/g, '').trim();
      if (st && /^[.,]?\d+/.test(st)) fTxt = st.replace(/^[^0-9]+/, '').slice(0, 6).replace('.', '');
    }
    if (!iTxt) return '';
    return fTxt ? iTxt + '.' + fTxt : iTxt;
  }
  function shopNameFromCard(card) {
    if (!card) return '';
    const se =
      card.querySelector('[class*="shopNameText--"]') ||
      card.querySelector('[class*="shopName--"][class*="Text"]');
    let t = se ? cleanTitle(se.innerText || se.textContent || '') : '';
    const snF = card.querySelector('[class*="shopName"]:not(script)');
    if ((!t || t.length < 2) && snF) {
      t = cleanTitle((snF.innerText || '').trim()).slice(0, 200);
    }
    return t.slice(0, 200);
  }
  function skipLine(line) {
    return (
      !line ||
      line.length < 6 ||
      /人付款|^\d+\+?人|^广东|^浙江|^江苏|^上海|^北京|包邮|公益宝贝|官方立减|券后价|店铺|进店|搜同款/i.test(line) ||
      /^找货源|^1688/.test(line) ||
      /^¥|^￥/.test(line)
    );
  }
  /** Khối chứa 1 ô SP: ô tìm kiếm thường có priceInt-- hoặc shopNameText-- */
  function findSearchCard(a) {
    let p = a.parentElement;
    for (let d = 0; d < 22 && p; d++, p = p.parentElement) {
      try {
        if (!p.contains(a)) continue;
        if (
          p.querySelector('[class*="priceInt--"]') ||
          p.querySelector('[class*="shopNameText--"]') ||
          p.querySelector('[class*="priceWrap--"], [class*="priceContainer"]')
        ) {
          return p;
        }
      } catch (e) {}
    }
    return (
      a.closest(
        '[class*="doubleCardWrapper"], [class*="cardContainer--"], ' +
          '[class*="CardWrapper"], [class*="Card--"], [class*="itemCard"], ' +
          '[class*="GoodsItem"], div[data-category="auctions"] div'
      ) || a.closest('div') ||
      a.parentElement
    );
  }
  function pickProductImg(card) {
    if (!card) return '';
    for (const im of card.querySelectorAll(
      'img[src*="gw.alicdn"], img[src*="imgextra"], img[data-src*="alicdn"], ' +
      'img[class*="pic"], img[class*="Pic"]'
    )) {
      const s =
        im.src ||
        im.getAttribute('data-src') ||
        im.getAttribute('data-ks-lazyload') ||
        '';
      if (!s || !s.includes('http')) continue;
      if (s.includes('atmosphere_center_image')) continue;
      if (s.includes('O1CN01CYtPWu1MUBqQAUK9D')) continue;
      if (im.closest('[class*="title--"], [class*="Title--"], [class*="shopIcon"]'))
        continue;
      return s.split('#')[0];
    }
    return '';
  }

  const anchors = Array.from(
    document.querySelectorAll(
      'a[href*="item.htm"], a[href*="item.taobao"], a[href*="detail.tmall"], a[href*="tmall.com/item"]'
    )
  );

  for (const a of anchors) {
    const hrefRaw = String(a.href || a.getAttribute('href') || '');
    let href = hrefRaw.split('#')[0];
    if (href.startsWith('//')) href = 'https:' + href;
    const m = href.match(/[?&]id=(\d+)/);
    if (!m) continue;
    const id = m[1];
    if (seen.has(id)) continue;
    seen.add(id);

    let title =
      cleanTitle(a.getAttribute('title') || '') ||
      cleanTitle(String(a.dataset && a.dataset.title ? a.dataset.title : ''));

    const card = findSearchCard(a);
    let img = '';

    let shop_name = '';

    if (card) {
      shop_name = shopNameFromCard(card);
      const tCandidates = [];
      card
        .querySelectorAll(
          '[class*="title--"], [class*="Title"], [class*="subtitle"], [class*="itemTitle"], h3'
        )
        .forEach((el) => {
          const tt = cleanTitle(el.innerText || '');
          if (tt.length > 12 && !/¥|￥|人付款/.test(tt)) tCandidates.push(tt);
        });
      for (const tt of tCandidates) {
        if (tt.length > title.length) title = tt.slice(0, 500);
      }
      if (!title || title.length < 8) {
        for (const line of (card.innerText || '').split(/\r?\n/)) {
          const L = cleanTitle(line);
          if (skipLine(L)) continue;
          if (L.length > title.length) title = L;
        }
      }
      img = pickProductImg(card) || '';

      let pr = '';
      let first = '';
      let best = '';
      const fullTxt = card.innerText || '';
      const lines = fullTxt.split(/\r?\n/);
      const splitPr = splitPriceFromDOM(card);
      for (const line of lines) {
        const L = line.trim();
        if (/[¥￥]\s*\d/.test(L) && pickPrice(L)) {
          const v = pickPrice(L);
          if (v && !best) best = v;
        }
      }
      if (!best) best = pickPrice(fullTxt);
      let hitCoupon = false;
      for (const raw of lines.map((x) => x.trim())) {
        const L = raw;
        if (/券后价|券后|到手价/.test(L)) hitCoupon = true;
        else if (hitCoupon && pickPrice(L)) {
          first = pickPrice(L);
          break;
        }
        if (/券|减|包邮|特惠/.test(L)) hitCoupon = false;
      }
      pr = splitPr || first || best || '';

      rows.push({
        item_id: id,
        shop_name: shop_name.slice(0, 200),
        title: title.slice(0, 420),
        url: href,
        price_text: pr,
        image_url: img,
      });
      continue;
    }

    rows.push({
      item_id: id,
      shop_name: '',
      title: title.slice(0, 420),
      url: href,
      price_text: '',
      image_url: '',
    });
  }
  return rows;
}
"""

_URL_ITEM_TB = re.compile(
    r"(?:https?:)?//item\.taobao\.com/item\.htm\?[^\s\"'<>]+", re.I
)
_URL_ITEM_TMALL = re.compile(
    r"(?:https?:)?//detail\.tmall\.com/item\.htm\?[^\s\"'<>]+", re.I
)


def _urls_with_scheme(raw: str) -> str:
    u = raw.strip().rstrip("\\,.);")
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://"):
        return "https://" + u[len("http://") :]
    return u


def _harvest_item_urls_from_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rx in (_URL_ITEM_TB, _URL_ITEM_TMALL):
        for m in rx.finditer(text):
            u = _urls_with_scheme(m.group(0))
            im = re.search(r"[?&]id=(\d+)", u)
            if not im:
                continue
            rows.append(
                {
                    "item_id": im.group(1),
                    "title": "",
                    "shop_name": "",
                    "url": u,
                    "price_text": "",
                    "image_url": "",
                }
            )
    return rows


def _merge_rows(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    ta, tb = str(a.get("title") or "").strip(), str(b.get("title") or "").strip()
    title = ta if len(ta) >= len(tb) else tb
    pa, pb = str(a.get("price_text") or "").strip(), str(b.get("price_text") or "").strip()
    price_text = pb if pb else pa
    ia, ib = str(a.get("image_url") or "").strip(), str(b.get("image_url") or "").strip()
    image_url = ib if ib else ia
    sa, sb = str(a.get("shop_name") or "").strip(), str(b.get("shop_name") or "").strip()
    shop_name = sa if len(sa) >= len(sb) else sb
    return {
        "item_id": str(a.get("item_id") or b.get("item_id") or ""),
        "title": title,
        "shop_name": shop_name,
        "price_text": price_text,
        "url": str(a.get("url") or b.get("url") or "").strip() or "",
        "image_url": image_url,
        "search_page": max(
            int(a.get("search_page") or 0), int(b.get("search_page") or 0)
        ),
        "pagination_note": str(a.get("pagination_note") or b.get("pagination_note") or ""),
    }


def _scroll_pagination_bar_into_view(page: Any) -> None:
    try:
        page.evaluate(
            """() => {
  const n = document.querySelector(
    '.next-pagination, [class*="next-pagination"], [class*="Pagination"]'
  );
  if (n) n.scrollIntoView({ block: 'end', behavior: 'instant' });
}"""
        )
        page.wait_for_timeout(450)
    except Exception:
        pass


def _click_taobao_search_page_number(
    page: Any, page_num: int, *, settle_ms: int = 4500
) -> bool:
    """Ấn nút số trang (Next UI): <button class="next-pagination-item" aria-label="第3页，共100页">."""
    if page_num < 2:
        return True
    _scroll_pagination_bar_into_view(page)
    label_core = f"第{page_num}页"
    pat = re.compile(re.escape(label_core))
    try:
        page.get_by_role("button", name=pat).first.click(timeout=16000)
        page.wait_for_timeout(settle_ms)
        return True
    except Exception:
        pass
    try:
        page.locator(
            f'button.next-pagination-item[aria-label*="{label_core}"]'
        ).first.click(timeout=16000)
        page.wait_for_timeout(settle_ms)
        return True
    except Exception:
        pass
    try:
        page.locator("button.next-pagination-item").filter(
            has=page.locator(f'span.next-btn-helper:text-is("{page_num}")')
        ).first.click(timeout=16000)
        page.wait_for_timeout(settle_ms)
        return True
    except Exception:
        return False


def _make_net_handler(bucket: List[Dict[str, Any]]) -> Any:
    allow = frozenset({"xhr", "fetch", "document"})

    def on_response(resp: Any) -> None:
        try:
            if resp.request.resource_type not in allow:
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
            and "itemId" not in text
            and "auctionId" not in text
        ):
            return
        bucket.extend(_harvest_item_urls_from_text(text))

    return on_response


def main() -> None:
    ap = argparse.ArgumentParser(description="Taobao s.taobao.com/search — N trang → Excel")
    ap.add_argument("--cookies", type=Path, required=True)
    ap.add_argument(
        "--url",
        required=True,
        help='URL đầy đủ ví dụ s.taobao.com/search?page=1&q=...&tab=all',
    )
    ap.add_argument("--pages", type=int, default=3, help="Số trang đầu (mặc định 3)")
    ap.add_argument("--out", type=Path, default=Path("taobao_search.xlsx"))
    ap.add_argument("--wait-ms", type=int, default=7000)
    ap.add_argument(
        "--scroll-rounds",
        type=int,
        default=44,
        help="Số lần wheel mỗi trang (~46 SP thường cần 35–50+ khi waterfall)",
    )
    ap.add_argument(
        "--scroll-pause-ms",
        type=int,
        default=260,
        help="Nghỉ sau mỗi lần wheel (ms)",
    )
    ap.add_argument(
        "--google-search-mode",
        choices=("serp", "synthetic", "none"),
        default="serp",
        help="serp=visit Google SERP rồi mở TB qua redirect google.com/url; synthetic=TB qua redirect Google (không qua SERP); none=Taobao URL trực tiếp.",
    )
    ap.add_argument(
        "--google-serp-each-page",
        action="store_true",
        help="Với google-search-mode=serp: trước mỗi SERP TB, goto lại trang kết quả Google (referer=SERP).",
    )
    ap.add_argument(
        "--page-step",
        type=int,
        default=48,
        metavar="N",
        help="Số ô/trang làm offset s=(page-1)*N trong chế độ URL (TB thường 44–48; thử chỉnh nếu lệch trang).",
    )
    ap.add_argument(
        "--pagination-nav",
        choices=("click", "url"),
        default="click",
        help="click=ấn nút trang (第2页/第3页…); url=goto URL (page+s). Headless hay dùng url.",
    )
    ap.add_argument("--headless", action="store_true")
    ap.add_argument(
        "--shop-name",
        default="",
        metavar="TEXT",
        help="Chỉ xuất dòng có shop_name không rỗng và chứa TEXT (chuỗi con).",
    )
    args = ap.parse_args()

    if not args.cookies.is_file():
        raise SystemExit(f"Không có cookie: {args.cookies}")
    if args.pages < 1:
        raise SystemExit("--pages >= 1")

    base_url = args.url.strip()
    cookies = _load_cookies(args.cookies)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium")

    all_flat: List[Dict[str, Any]] = []
    pagination_note_global = ""

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 920},
        )
        page = ctx.new_page()
        net_bucket: List[Dict[str, Any]] = []
        page.on("response", _make_net_handler(net_bucket))

        page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=120_000)
        ctx.add_cookies(cookies)

        google_serp_url: Optional[str] = None
        u0 = _ensure_scheme(base_url.split("#")[0])
        use_google_gateway = args.google_search_mode != "none"

        if args.google_search_mode == "none":
            pass
        elif args.google_search_mode == "synthetic":
            pass
        elif args.google_search_mode == "serp":
            try:
                qd = dict(parse_qsl(urlparse(u0).query, keep_blank_values=True))
                q_txt = (qd.get("q") or "").strip()
                if not q_txt:
                    q_txt = "taobao s.taobao.com search"
                qs = quote(f"{q_txt} taobao s.taobao.com")
                page.goto(
                    f"https://www.google.com/search?q={qs}&hl=zh-CN&igu=1",
                    wait_until="domcontentloaded",
                    timeout=90_000,
                )
                page.wait_for_timeout(1200)
                google_serp_url = page.url
            except Exception:
                google_serp_url = None

        settle = max(2800, int(args.wait_ms))

        def _open_taobao_search(u: str, navigation: Dict[str, Any]) -> None:
            if use_google_gateway:
                page.goto(_via_google_redirect_url(u), **navigation)
            else:
                page.goto(u, **navigation)

        for pidx in range(1, args.pages + 1):
            nav: Dict[str, Any] = {
                "wait_until": "domcontentloaded",
                "timeout": 180_000,
            }

            if (
                google_serp_url
                and args.google_serp_each_page
                and args.google_search_mode == "serp"
            ):
                page.goto(
                    google_serp_url,
                    wait_until="domcontentloaded",
                    timeout=120_000,
                )
                page.wait_for_timeout(450)

            if pidx == 1:
                target = _with_search_page(base_url, 1, page_step=args.page_step)
                _open_taobao_search(target, nav)
            elif args.pagination_nav == "click":
                if not _click_taobao_search_page_number(
                    page, pidx, settle_ms=settle
                ):
                    target = _with_search_page(base_url, pidx, page_step=args.page_step)
                    _open_taobao_search(target, nav)
            else:
                target = _with_search_page(base_url, pidx, page_step=args.page_step)
                _open_taobao_search(target, nav)

            page.wait_for_timeout(max(0, args.wait_ms))

            for _ in range(max(12, args.scroll_rounds)):
                page.mouse.wheel(0, 1650)
                page.wait_for_timeout(max(120, args.scroll_pause_ms))
            try:
                page.evaluate(
                    "window.scrollTo(0, Math.max(document.documentElement.scrollHeight,"
                    "document.body.scrollHeight))"
                )
            except Exception:
                pass
            page.wait_for_timeout(900)

            hint = page.evaluate(_EXTRACTION_NOTE_JS)
            if isinstance(hint, dict) and hint.get("pagination_guess"):
                pagination_note_global = str(hint.get("pagination_guess") or "").strip()

            rows = page.evaluate(_EXTRACT_JS)
            net_rows = list(net_bucket)
            net_bucket.clear()

            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict):
                        rr = dict(r)
                        rr["search_page"] = pidx
                        rr["pagination_note"] = pagination_note_global
                        all_flat.append(rr)
            for r in net_rows:
                rr = dict(r)
                rr["search_page"] = pidx
                rr["pagination_note"] = pagination_note_global
                all_flat.append(rr)

            html_blob = ""
            try:
                html_blob = page.content()
            except Exception:
                html_blob = ""
            for r in _harvest_item_urls_from_text(html_blob):
                rr = dict(r)
                rr["search_page"] = pidx
                rr["pagination_note"] = pagination_note_global
                all_flat.append(rr)

        browser.close()

    by_id: Dict[str, Dict[str, Any]] = {}
    for r in all_flat:
        iid = str(r.get("item_id") or "").strip()
        if not iid:
            continue
        if iid not in by_id:
            by_id[iid] = dict(r)
        else:
            by_id[iid] = _merge_rows(by_id[iid], r)

    rows_out = list(by_id.values())
    shop_filter = str(args.shop_name or "").strip()
    if shop_filter:
        before = len(rows_out)
        rows_out = [
            r
            for r in rows_out
            if shop_filter in str(r.get("shop_name") or "").strip()
        ]
        if before and not rows_out:
            raise SystemExit(
                f"Sau --shop-name {shop_filter!r}: 0 dòng (trước lọc {before}). "
                "Thử chỉnh TEXT hoặc xem có lấy được shop_name trong UI không (--headless tắt)."
            )

    if not rows_out:
        raise SystemExit(
            "0 sản phẩm — thử bỏ --headless, làm mới cookie, hoặc tăng --wait-ms."
        )

    cols = [
        "item_id",
        "shop_name",
        "title",
        "price_text",
        "url",
        "image_url",
        "search_page",
        "pagination_note",
    ]
    df = pd.DataFrame(rows_out)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df = df[cols]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(args.out, index=False, engine="openpyxl")
    tail = ""
    if shop_filter:
        tail = f" (lọc shop_name chứa {shop_filter!r})"
    print(
        f"Wrote {len(df)} unique rows (from {args.pages} page(s)) "
        f"pagination≈«{pagination_note_global}»"
        f"{tail} → {args.out.resolve()}"
    )


if __name__ == "__main__":
    main()
