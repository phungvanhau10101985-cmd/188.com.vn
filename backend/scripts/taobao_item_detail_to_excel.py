"""
Chi tiết một SP Taobao (`item.taobao.com/item.htm?id=…`) → Excel **một dòng**, nhiều cột theo trường.

**Cột chính (skin PC tbpc ~2025):** tên shop, URL shop, tiêu đề, giá 券后/优惠前 (tệ), gợi ý USD,
coupon, giao hàng, SKU (JSON + JSON màu + size nối phẩy), 参数 (JSON nổi bật + bảng),
ảnh thumbnail gallery, ảnh chính, ảnh khu 图文详情, merge ảnh fallback.

Kèm cột hỗ trợ: meta, giá rải DOM, gợi ý giá từ XHR/fetch, json-ld, loader hints.

Thu thập đa kênh: DOM + cuộn lazy + bấm tab «图文详情» + response XHR/fetch có `id` SP.
Một số skin che giá — dùng `price_hints_from_network_xhr_fetch`.

  cd backend && set PYTHONPATH=. && python scripts/taobao_item_detail_to_excel.py ^
    --cookies runtime\\taobao_cookies_session.json ^
    --url "https://item.taobao.com/item.htm?id=941739988242" ^
    --google-search-mode serp ^
    --out runtime\\taobao_item.xlsx

`--google-search-mode serp` (mặc định): mở Google Search rồi vào item qua **`google.com/url?…` redirect**. Nếu gặp **重定向声明** / **验证码拦截**, mở **context Playwright mới** và tải lại **trực tiếp** `item.htm` (ổn với `--headless` + cookie).

`synthetic`: chỉ redirect Google, không vào SERP; vẫn có **fallback context** như trên. `none`: luôn taobao.com → item (nhẹ nhất khi có cookie).

Cookie: JSON export như các script Taobao khác — không commit.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import quote, urlparse

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
    if domain.startswith("http"):
        domain = urlparse(domain).hostname or ".taobao.com"
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
        raise SystemExit("Cookie JSON phải là array hoặc object có «cookies»")
    out: List[Dict[str, Any]] = []
    for c in arr:
        nc = _normalize_playwright_cookie(c) if isinstance(c, dict) else None
        if nc:
            out.append(nc)
    return out


def _seed_taobao_tmall_cookies(ctx: Any, page: Any, cookies: List[Dict[str, Any]]) -> None:
    """Playwright chỉ gắn cookie tin cậy khi đã mở đúng origin (taobao.com / tmall.com)."""
    if not cookies:
        page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=180_000)
        return
    tb_bucket: List[Dict[str, Any]] = []
    tm_bucket: List[Dict[str, Any]] = []
    for c in cookies:
        dom = str(c.get("domain") or "").lower()
        if "tmall.com" in dom:
            tm_bucket.append(c)
        else:
            tb_bucket.append(c)
    if tb_bucket:
        page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=180_000)
        ctx.add_cookies(tb_bucket)
    if tm_bucket:
        page.goto("https://www.tmall.com/", wait_until="domcontentloaded", timeout=180_000)
        ctx.add_cookies(tm_bucket)
    if not tb_bucket and not tm_bucket:
        page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=180_000)


def _ensure_scheme(url: str) -> str:
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    if not u.startswith("http"):
        return "https://" + u
    return u


def _via_google_redirect_url(destination: str) -> str:
    return (
        "https://www.google.com/url?sa=t&source=web&rct=j&url="
        + quote(_ensure_scheme(destination), safe="")
    )


def _item_page_looks_like_redirect_placeholder(extracted: Dict[str, Any]) -> bool:
    """TB đôi khi trả trang không phải SP: redirect 声明, captcha 验证码, v.v."""
    if not extracted:
        return True
    dt = str(extracted.get("document_title") or "")
    if "重定向" in dt:
        return True
    if "验证码" in dt or "安全验证" in dt:
        return True
    if "登录" in dt or "请登录" in dt or "請登錄" in dt:
        return True
    cands = extracted.get("title_candidates") or []
    if cands and isinstance(cands[0], str):
        h = cands[0][:120]
        if "重定向" in h or "验证码" in h or "拦截" in h:
            return True
    st = extracted.get("structured") or {}
    pt = str(st.get("product_title") or "").strip() if isinstance(st, dict) else ""
    if pt == "重定向声明" or dt.strip() == "重定向声明":
        return True
    if isinstance(st, dict) and not pt and not str(st.get("shop_name") or "").strip():
        # có thể vẫn loading; chỉ retry khi title rõ là gate
        if "验证" in dt or "验证" in str(extracted.get("document_title") or ""):
            return True
    return False


def _item_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"[?&]id=(\d+)", url.replace("&amp;", "&"))
    return m.group(1) if m else None


_EXTRACT_JS = r"""
() => {
  function absUrl(u) {
    if (!u) return '';
    u = String(u).trim();
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('http://')) return 'https://' + u.slice(7);
    return u;
  }
  function uniqUrl(arr) {
    const seen = new Set(), out = [];
    for (const u of arr) {
      const a = absUrl(u);
      const k = a.split('?')[0];
      if (!a.startsWith('http') || seen.has(k)) continue;
      seen.add(k);
      out.push(a);
      if (out.length >= 120) break;
    }
    return out;
  }

  /* --- Structured (skin tbpc Detail 2025) --- */
  const st = {
    shop_name: '',
    shop_category_url: '',
    product_title: '',
    price_after_coupon_cny: '',
    price_before_discount_cny: '',
    oversea_price_hint: '',
    sub_title_promo_lines: [],
    coupons_lines: [],
    shipping_line: '',
    sku_groups: [],
    params_emphasis: [],
    params_general: [],
    gallery_thumbnails: [],
    main_image: '',
    detail_images: [],
  };

  const shopNm = document.querySelector('[class*="shopName--"]');
  if (shopNm)
    st.shop_name = (
      shopNm.getAttribute('title') ||
      (shopNm.innerText || '').trim() ||
      ''
    ).trim();

  const shopLn = document.querySelector(
    'a[href*="shop"][href*="category.htm"], [class*="detailWrap--"][href*="shop"]'
  );
  if (shopLn && shopLn.href) st.shop_category_url = absUrl(shopLn.href);

  const mt = document.querySelector('[class*="mainTitle--"]');
  if (mt)
    st.product_title = (
      mt.getAttribute('title') ||
      (mt.innerText || '').trim() ||
      ''
    ).trim();

  const np = document.querySelector('[class*="normalPrice--"]');
  if (np) {
    const hi = np.querySelector('[class*="highlightPrice--"]');
    if (hi) {
      const txs = [...hi.querySelectorAll('[class*="text--"]')]
        .map((t) => (t.innerText || '').trim())
        .filter((x) => /^\d+(?:\.\d+)?$/.test(x));
      if (txs.length) st.price_after_coupon_cny = txs[txs.length - 1];
    }
    const sub = np.querySelector('[class*="subPrice--"]');
    if (sub) {
      const txs = [...sub.querySelectorAll('[class*="text--"]')]
        .map((t) => (t.innerText || '').trim())
        .filter((x) => /^\d+(?:\.\d+)?$/.test(x));
      if (txs.length) st.price_before_discount_cny = txs[txs.length - 1];
    }
  }

  const op = document.querySelector('[class*="overseaPriceText--"], [class*="overseaPrice--"] span');
  if (op) st.oversea_price_hint = (op.innerText || '').trim().slice(0, 200);

  const subTi = document.querySelector('[class*="subTitleInnerWrap--"]');
  if (subTi) {
    subTi.querySelectorAll('[class*="itemInfo--"] span, [class*="itemInfo--"]').forEach((el) => {
      const t = (el.innerText || '').trim();
      if (t && t.length < 160) st.sub_title_promo_lines.push(t);
    });
  }

  document.querySelectorAll('[class*="CouponItem--"]').forEach((el) => {
    const t = (
      el.getAttribute('title') ||
      el.innerText ||
      ''
    ).trim();
    if (t && t.length < 200) st.coupons_lines.push(t);
  });

  const ship = document.querySelector('[class*="DomesticDelivery--"] [class*="shipping--"], [class*="DomesticDelivery--"]');
  if (ship) {
    let s = (ship.innerText || '').replace(/\s+/g, ' ').trim();
    if (s.length > 8 && s.length < 500) st.shipping_line = s;
  }

  document.querySelectorAll('[class*="skuItem--"]').forEach((block) => {
    const labSp = block.querySelector('[class*="ItemLabel--"] span');
    const label = labSp
      ? (
          labSp.getAttribute('title') ||
          labSp.innerText ||
          ''
        ).trim()
      : '';
    const values = [];
    block.querySelectorAll('[class*="valueItem--"]').forEach((vi) => {
      const vid = vi.getAttribute('data-vid') || '';
      let img = '';
      const imgEl =
        vi.querySelector('img[class*="valueItemImg--"]') ||
        vi.querySelector('img[src*="alicdn"]') ||
        vi.querySelector('img[src*="gw.alicdn"]');
      if (imgEl)
        img = absUrl(imgEl.src || imgEl.getAttribute('data-src') || '');
      const vt = vi.querySelector('[class*="valueItemText--"]');
      let text = '';
      if (vt) text = (vt.getAttribute('title') || vt.innerText || '').trim();
      const cr = vi.querySelector('[class*="cornerText--"]');
      let corner = '';
      if (cr)
        corner = (
          cr.getAttribute('title') ||
          cr.innerText ||
          ''
        ).trim();
      if (text) values.push({ vid, text, img, corner });
    });
    if (label && values.length) st.sku_groups.push({ label, values });
  });

  document.querySelectorAll('[class*="emphasisParamsInfoItem--"]').forEach((el) => {
    const tMain = el.querySelector('[class*="emphasisParamsInfoItemTitle--"]');
    const tSub = el.querySelector('[class*="emphasisParamsInfoItemSubTitle--"]');
    if (!tMain || !tSub) return;
    const v = (tMain.getAttribute('title') || tMain.innerText || '').trim();
    const n = (tSub.getAttribute('title') || tSub.innerText || '').trim();
    if (v && n) st.params_emphasis.push({ name: n, value: v });
  });

  document.querySelectorAll('[class*="generalParamsInfoItem--"]').forEach((el) => {
    const tTit = el.querySelector('[class*="generalParamsInfoItemTitle--"]');
    const tSub = el.querySelector('[class*="generalParamsInfoItemSubTitle--"]');
    if (!tTit || !tSub) return;
    const n = (tTit.getAttribute('title') || tTit.innerText || '').trim();
    const v = (tSub.getAttribute('title') || tSub.innerText || '').trim();
    if (n && v) st.params_general.push({ name: n, value: v });
  });

  document.querySelectorAll('img[class*="thumbnailPic--"]').forEach((im) => {
    const u = absUrl(im.src);
    if (u) st.gallery_thumbnails.push(u);
  });
  st.gallery_thumbnails = uniqUrl(st.gallery_thumbnails).slice(0, 48);

  const mp =
    document.querySelector('img[id="mainPicImageEl"], img[class*="mainPic--"]');
  if (mp) st.main_image = absUrl(mp.src);

  const detailRoot =
    document.querySelector('#imageTextInfo-content') ||
    document.querySelector('.descV8-container') ||
    document.querySelector('.desc-root');
  const dImgs = [];
  if (detailRoot) {
    detailRoot.querySelectorAll('img[src], img[data-src]').forEach((img) => {
      const raw = img.getAttribute('data-src') || img.src || '';
      const u = absUrl(raw);
      if (!u || u.includes('s.gif') || u.includes('data:')) return;
      dImgs.push(u);
    });
  }
  st.detail_images = uniqUrl(dImgs).slice(0, 100);

  /* --- Fallback / enrichment (meta + ô giá khác + ảnh rộng) --- */
  const meta = {};
  document.querySelectorAll('meta[property^="og:"],meta[name]').forEach((m) => {
    const k = m.getAttribute('property') || m.getAttribute('name');
    const c = (m.getAttribute('content') || '').trim();
    if (k && c) meta[k] = c.slice(0, 2000);
  });

  const titleCandidates = [];
  if (st.product_title) titleCandidates.push(st.product_title);
  const h = document.querySelector('h1');
  if (h) titleCandidates.push((h.innerText || '').trim().split('\n')[0].slice(0, 800));
  document.querySelectorAll('[class*="ItemTitle"]').forEach((el) => {
    const t = (el.innerText || '').trim();
    if (t.length >= 15 && t.length < 900) titleCandidates.push(t.split('\n')[0]);
  });

  const priceBits = [];
  document
    .querySelectorAll('[class*="price"],[class*="Price"],[data-spm*="price"]')
    .forEach((el) => {
      const t = (el.innerText || '').trim().replace(/\s+/g, ' ');
      if (!t || t.length > 120) return;
      if (/^\[[^\]]*#/.test(t)) return;
      if (/¥|￥|元|\d/.test(t)) priceBits.push(t);
    });

  const salesHints = [];
  document.body.innerText.split('\n').forEach((line) => {
    if (
      (/付款|人已购|月销量|累计销量|sold/i.test(line)) &&
      /\d/.test(line) &&
      line.length < 160
    )
      salesHints.push(line.trim());
  });

  const videoUrl = meta['og:video:url'] || meta['og:video'] || '';
  let jsonLdSnippet = '';
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
    jsonLdSnippet += (s.textContent || '') + ' ';
  });

  let loaderHints = '';
  Array.from(document.scripts)
    .slice(0, 80)
    .forEach((s) => {
      const t = s.textContent || '';
      if (
        t.includes('skuMap') ||
        t.includes('priceText') ||
        (t.includes('itemId') && t.length > 2000)
      ) {
        loaderHints += t.slice(0, 1800) + '---LOADER_SPLIT---';
      }
    });
  if (loaderHints.length > 28000) loaderHints = loaderHints.slice(0, 28000);

  const wideGal = [];
  const ogi = meta['og:image'];
  if (ogi) wideGal.push(absUrl(ogi));
  document
    .querySelectorAll(
      'img[src*="alicdn"], img[src*="gw.alicdn"], img[data-src*="alicdn"]'
    )
    .forEach((img) => {
      const u = absUrl(img.getAttribute('data-src') || img.src || '');
      if (
        !u ||
        !u.startsWith('http') ||
        u.includes('/icon/') ||
        u.includes('sns_logo')
      )
        return;
      wideGal.push(u);
    });
  const gallery_fallback_wide = uniqUrl(wideGal).slice(0, 96);

  return {
    structured: st,
    gallery_fallback_wide,
    document_title: (document.title || '').slice(0, 900),
    meta_json: meta,
    title_candidates: [...new Set(titleCandidates.filter(Boolean))].slice(0, 14),
    price_snippets: [...new Set(priceBits)].slice(0, 24),
    sales_hints: [...new Set(salesHints)].slice(0, 12),
    video_url_display: String(videoUrl).slice(0, 500),
    json_ld_snippet: jsonLdSnippet.trim().slice(0, 32000),
    inline_loader_hints_truncated: loaderHints,
  };
}
"""


def _truncate_cell(s: str, max_chars: int) -> str:
    s = str(s or "")
    return s if len(s) <= max_chars else s[: max_chars - 30] + "\n...[truncated]"


def _dedupe_ordered(urls: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for u in urls:
        u = (u or "").strip()
        k = u.split("?")[0]
        if not u.startswith("http") or k in seen:
            continue
        seen.add(k)
        out.append(u)
    return out


def _regex_prices_from_network(text: str, cap: int = 40) -> List[str]:
    found: List[str] = []
    for pat in (
        r'"priceText"\s*:\s*"([^"]+)"',
        r'"promotionPrice"\s*:\s*{[^}]*"price"\s*:\s*"?([\d.]+)',
        r'"price"\s*:\s*{[^}]*"priceText"\s*:\s*"([^"]*)"',
        r'"originPrice"\s*:\s*{[^}]*"priceText"\s*:\s*"([^"]*)"',
    ):
        for m in re.finditer(pat, text, flags=re.I):
            found.append((m.group(1) if m.lastindex else "").strip())
    # số trong context ¥ trong text
    for m in re.finditer(r"¥\s*([\d.,]+)|￥\s*([\d.,]+)", text):
        v = (m.group(1) or m.group(2) or "").replace(",", "").strip()
        if v:
            found.append(v)
    out: List[str] = []
    seen: Set[str] = set()
    for x in found:
        if x and len(x) < 80 and x not in seen:
            seen.add(x)
            out.append(x)
            if len(out) >= cap:
                break
    return out


def _uniq_join(parts: List[str], *, sep: str = " | ", cap: int = 40) -> str:
    seen: Set[str] = set()
    out: List[str] = []
    for p in parts:
        s = str(p).strip()
        if not s or len(s) > 200 or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= cap:
            break
    return sep.join(out)


def _sku_colors_sizes(sku_groups: Any) -> tuple[List[Any], List[str]]:
    colors: List[Any] = []
    sizes: List[str] = []
    if not isinstance(sku_groups, list):
        return colors, sizes
    for g in sku_groups:
        if not isinstance(g, dict):
            continue
        lab = str(g.get("label") or "")
        vals = g.get("values")
        vs = vals if isinstance(vals, list) else []
        if "颜色" in lab:
            colors = vs
        if "尺码" in lab:
            for v in vs:
                if isinstance(v, dict) and v.get("text"):
                    sizes.append(str(v["text"]).strip())
    seen: Set[str] = set()
    sizes_u: List[str] = []
    for s in sizes:
        if s and s not in seen:
            seen.add(s)
            sizes_u.append(s)
    return colors, sizes_u


def _scroll_detail_and_extract(page: Any, wait_ms: int) -> Dict[str, Any]:
    page.wait_for_timeout(max(0, wait_ms))
    for _ in range(14):
        page.mouse.wheel(0, 520)
        page.wait_for_timeout(200)
    try:
        page.evaluate(
            "window.scrollTo(0, Math.max(document.documentElement.scrollHeight,document.body.scrollHeight))"
        )
    except Exception:
        pass
    page.wait_for_timeout(900)
    try:
        page.locator('[class*="tabTitle--"]').filter(has_text="图文详情").first.click(
            timeout=5000
        )
    except Exception:
        try:
            page.get_by_text("图文详情", exact=True).first.click(timeout=4000)
        except Exception:
            pass
    page.wait_for_timeout(1500)
    for _ in range(18):
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(160)
    try:
        page.evaluate(
            "window.scrollTo(0, Math.max(document.documentElement.scrollHeight,document.body.scrollHeight))"
        )
    except Exception:
        pass
    page.wait_for_timeout(1000)

    extracted_raw = page.evaluate(_EXTRACT_JS)
    return extracted_raw if isinstance(extracted_raw, dict) else {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Taobao item.htm → một dòng Excel")
    ap.add_argument("--url", required=True, help="URL item.taobao.com/…")
    ap.add_argument("--out", type=Path, default=Path("taobao_item_detail.xlsx"))
    ap.add_argument("--cookies", type=Path, default=None)
    ap.add_argument("--wait-ms", type=int, default=9000)
    ap.add_argument(
        "--google-search-mode",
        choices=("serp", "synthetic", "none"),
        default="serp",
        help="serp=Google SERP rồi item qua redirect; synthetic=redirect thôi; "
        "none=trực tiếp. Nếu redirect dính gate, tự fallback context sạch → item.",
    )
    ap.add_argument("--headless", action="store_true")
    args = ap.parse_args()

    item_id = _item_id_from_url(args.url)
    if not item_id:
        raise SystemExit("URL thiếu id= hoặc không hợp lệ")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("pip install playwright && playwright install chromium")

    cookies: List[Dict[str, Any]] = []
    if args.cookies and args.cookies.is_file():
        cookies = _load_cookies(args.cookies)

    bodies: List[str] = []

    def on_response(resp: Any) -> None:
        try:
            if resp.request.resource_type not in ("xhr", "fetch", "document"):
                return
            b = resp.body()
            if len(b) > 3_600_000:
                return
            t = b.decode("utf-8", errors="ignore")
        except Exception:
            return
        if item_id not in t:
            return
        if len(bodies) >= 40:
            return
        bodies.append(t)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=["--disable-blink-features=AutomationControlled"])
        _ua_chrome = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        _vp = {"width": 1440, "height": 920}
        ctx = browser.new_context(locale="zh-CN", user_agent=_ua_chrome, viewport=_vp)
        page = ctx.new_page()
        page.on("response", on_response)

        _seed_taobao_tmall_cookies(ctx, page, cookies)

        item_url_clean = args.url.strip().split("#")[0]
        nav: Dict[str, Any] = {
            "wait_until": "domcontentloaded",
            "timeout": 180_000,
        }

        if args.google_search_mode == "serp":
            try:
                host = (urlparse(item_url_clean).hostname or "").lower()
                q_label = host if host.endswith("tmall.com") else "item.taobao.com"
                q = quote(f"{q_label} {item_id}")
                page.goto(
                    f"https://www.google.com/search?q={q}&hl=zh-CN&igu=1",
                    wait_until="domcontentloaded",
                    timeout=90_000,
                )
                page.wait_for_timeout(1400)
            except Exception:
                pass

        if args.google_search_mode == "none":
            page.goto(item_url_clean, **nav)
        else:
            page.goto(_via_google_redirect_url(item_url_clean), **nav)
        extracted: Dict[str, Any] = _scroll_detail_and_extract(page, args.wait_ms)

        if _item_page_looks_like_redirect_placeholder(extracted):
            ctx_fb = browser.new_context(locale="zh-CN", user_agent=_ua_chrome, viewport=_vp)
            pfb = ctx_fb.new_page()
            pfb.on("response", on_response)
            _seed_taobao_tmall_cookies(ctx_fb, pfb, cookies)
            pfb.goto(item_url_clean, **nav)
            extracted = _scroll_detail_and_extract(pfb, max(2800, args.wait_ms))
            pfb.close()
            ctx_fb.close()
        browser.close()

    if not isinstance(extracted, dict):
        extracted = {}

    meta = extracted.get("meta_json") or {}
    if not isinstance(meta, dict):
        meta = {}
    st = extracted.get("structured") or {}
    if not isinstance(st, dict):
        st = {}

    net_blob = "\n".join(bodies[:25])
    net_prices = _regex_prices_from_network(net_blob)

    dom_title = str(st.get("product_title") or "").strip()

    title_pick = dom_title[:2000]
    if not title_pick:
        for t in extracted.get("title_candidates") or []:
            tt = str(t).strip()
            if len(tt) > len(title_pick):
                title_pick = tt[:2000]
    if not title_pick:
        title_pick = (
            meta.get("og:title") or str(extracted.get("document_title") or "")
        ).strip()[:2000]

    sku_groups = st.get("sku_groups")
    sku_groups_list = sku_groups if isinstance(sku_groups, list) else []
    sku_colors, sku_sizes_flat = _sku_colors_sizes(sku_groups_list)

    price_dom_flat = _uniq_join(
        [str(x) for x in (extracted.get("price_snippets") or [])], sep=" | ", cap=24
    )

    thumbs = (
        list(st.get("gallery_thumbnails") or [])
        if isinstance(st.get("gallery_thumbnails"), list)
        else []
    )
    fallback_g = extracted.get("gallery_fallback_wide") or []
    merged_gallery = _dedupe_ordered(
        [str(st.get("main_image") or "")]
        + [str(x) for x in thumbs]
        + [str(x) for x in (fallback_g if isinstance(fallback_g, list) else [])]
    )

    max_cell = 28000

    row = {
        "item_id": item_id,
        "url": args.url.strip().split("#")[0],
        "shop_name": str(st.get("shop_name") or "")[:900],
        "shop_category_url": str(st.get("shop_category_url") or "")[:2000],
        "product_title_dom": dom_title[:2000],
        "title_chosen": title_pick[:2000],
        "price_after_coupon_cny": str(st.get("price_after_coupon_cny") or "")[:64],
        "price_before_discount_cny": str(st.get("price_before_discount_cny") or "")[:64],
        "oversea_price_hint": str(st.get("oversea_price_hint") or "")[:500],
        "coupons_pipe": _truncate_cell(
            " | ".join(str(x) for x in (st.get("coupons_lines") or [])[:24]),
            max_cell,
        ),
        "shipping_line": str(st.get("shipping_line") or "")[:2000],
        "sub_title_promo_pipe": _truncate_cell(
            " | ".join(str(x) for x in (st.get("sub_title_promo_lines") or [])[:20]),
            max_cell,
        ),
        "sku_groups_json": _truncate_cell(
            json.dumps(sku_groups_list, ensure_ascii=False),
            max_cell,
        ),
        "sku_colors_variants_json": _truncate_cell(
            json.dumps(sku_colors if sku_colors else [], ensure_ascii=False),
            max_cell,
        ),
        "sku_sizes_joined_comma": ", ".join(sku_sizes_flat)[:800],
        "params_emphasis_json": _truncate_cell(
            json.dumps(st.get("params_emphasis") or [], ensure_ascii=False),
            max_cell,
        ),
        "params_general_json": _truncate_cell(
            json.dumps(st.get("params_general") or [], ensure_ascii=False),
            max_cell,
        ),
        "main_image_url": str(st.get("main_image") or "")[:2500],
        "gallery_thumbnails_json": _truncate_cell(
            json.dumps(thumbs, ensure_ascii=False), max_cell
        ),
        "detail_section_images_json": _truncate_cell(
            json.dumps(
                (
                    list(st.get("detail_images") or [])
                    if isinstance(st.get("detail_images"), list)
                    else []
                ),
                ensure_ascii=False,
            ),
            max_cell,
        ),
        "gallery_merged_fallback_json": _truncate_cell(
            json.dumps(merged_gallery, ensure_ascii=False),
            max_cell,
        ),
        "document_title": str(extracted.get("document_title") or "")[:900],
        "og_description": str(meta.get("og:description") or "")[:2000],
        "price_dom_other_snippets": _truncate_cell(price_dom_flat[:8000], max_cell),
        "price_hints_from_network_xhr_fetch": _truncate_cell(
            " | ".join(net_prices)[:6000],
            max_cell,
        ),
        "sales_hints": _truncate_cell(
            " | ".join(str(x) for x in (extracted.get("sales_hints") or [])[:14]),
            max_cell,
        ),
        "video_url": str(extracted.get("video_url_display") or "")[:500],
        "og_image_meta": str(meta.get("og:image") or "")[:900],
        "json_ld_snippet_truncated": _truncate_cell(
            str(extracted.get("json_ld_snippet") or ""), max_cell
        ),
        "inline_loader_hints_truncated": _truncate_cell(
            str(extracted.get("inline_loader_hints_truncated") or ""), max_cell
        ),
    }

    df = pd.DataFrame([row])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(args.out, index=False, engine="openpyxl")
    print(f"Wrote 1 row ({item_id}) → {args.out.resolve()}")


if __name__ == "__main__":
    main()
