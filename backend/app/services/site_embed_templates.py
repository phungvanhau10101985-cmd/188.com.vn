"""
Sinh HTML/JS chuẩn từ chỉ mã (ID token) — khung dựng sẵn theo platform/category.
Nếu admin dán nguyên HTML (thẻ <script>, <meta>...), giữ nguyên (tương thích xưa).
"""
from __future__ import annotations

import json
import html
import re
from typing import List, Sequence, Tuple

from app.models.site_embed_code import SiteEmbedCode

PlacementHtml = Tuple[str, str]

# Không bao giờ đưa ra API /embed-codes/public (chỉ dùng máy chủ)
INTERNAL_ONLY_CATEGORIES = frozenset({"capi_token"})


def _pla(row: SiteEmbedCode) -> str:
    p = (row.placement or "head").strip().lower()
    if p in ("head", "body_open", "body_close"):
        return p
    return "head"


def looks_like_pasted_html(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    tl = t.lower()
    if tl.startswith("<"):
        return True
    if "<script" in tl or "<iframe" in tl or "<meta" in tl or "<noscript" in tl or "<link" in tl:
        return True
    return False


def _norm_ga4_measurement_id(s: str) -> str | None:
    u = (s or "").strip().upper().replace(" ", "")
    if re.match(r"^G-[A-Z0-9]+$", u):
        return u
    return None


def _norm_gtm(s: str) -> str | None:
    u = s.strip().upper()
    return u if re.match(r"^GTM-[A-Z0-9]+$", u) else None


def _norm_aw(s: str) -> str | None:
    u = s.strip().upper()
    return u if re.match(r"^AW-[0-9]+$", u) else None


def expand_ga4(measurement_id: str) -> List[PlacementHtml]:
    gid = _norm_ga4_measurement_id(measurement_id)
    if not gid:
        return []
    esc = html.escape(gid, quote=True)
    snippet = (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc}"></script>'
        "<script>"
        "window.dataLayer = window.dataLayer || [];"
        "function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());"
        f"gtag('config', '{esc}');"
        "</script>"
    )
    return [("head", snippet)]


def expand_gtm(container_id: str) -> List[PlacementHtml]:
    cid = _norm_gtm(container_id)
    if not cid:
        return []
    esc = html.escape(cid, quote=True)
    head_js = (
        "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':"
        "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],"
        'j=d.createElement(s),dl=l!="dataLayer"?"&l="+l:"";j.async=true;j.src='
        '"https://www.googletagmanager.com/gtm.js?id="+i+dl;f.parentNode.insertBefore(j,f);'
        "})(window,document,'script','dataLayer','"
        f"{esc}"
        "');</script>"
    )
    noscript = (
        f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={esc}" '
        'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>'
    )
    return [("head", head_js), ("body_open", noscript)]


def expand_google_ads_aw(aw_id: str) -> List[PlacementHtml]:
    aid = _norm_aw(aw_id)
    if not aid:
        return []
    esc = html.escape(aid, quote=True)
    snippet = (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={esc}"></script>'
        "<script>"
        "window.dataLayer = window.dataLayer || [];"
        "function gtag(){dataLayer.push(arguments);}"
        "gtag('js', new Date());"
        f"gtag('config', '{esc}');"
        "</script>"
    )
    return [("head", snippet)]


def expand_google_site_verification(token: str) -> List[PlacementHtml]:
    t = token.strip()
    if not t:
        return []
    esc = html.escape(t, quote=True)
    return [("head", f'<meta name="google-site-verification" content="{esc}" />')]


def expand_google_merchant_center_verification(token: str) -> List[PlacementHtml]:
    """Merchant Center HTML tag verification — Google dùng cùng định dạng meta google-site-verification."""
    return expand_google_site_verification(token)


def expand_facebook_pixel(pixel_id: str) -> List[PlacementHtml]:
    pid = re.sub(r"\D", "", (pixel_id or "").strip())
    if not pid:
        return []
    # pixel id chỉ số — tránh inject
    snippet = (
        "<script>"
        "!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?"
        "n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;"
        "n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;"
        "t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}"
        "(window, document,'script','https://connect.facebook.net/en_US/fbevents.js');"
        f"fbq('init', '{pid}');"
        "fbq('track', 'PageView');"
        "</script>"
        f'<noscript><img height="1" width="1" style="display:none" '
        f'src="https://www.facebook.com/tr?id={pid}&ev=PageView&noscript=1" /></noscript>'
    )
    return [("head", snippet)]


def expand_facebook_domain_verification(token: str) -> List[PlacementHtml]:
    t = token.strip()
    if not t:
        return []
    esc = html.escape(t, quote=True)
    return [("head", f'<meta name="facebook-domain-verification" content="{esc}" />')]


def expand_facebook_chat_page_id(page_id: str) -> List[PlacementHtml]:
    pid = re.sub(r"\D", "", (page_id or "").strip())
    if not pid:
        return []
    snippet = (
        '<div id="fb-root"></div>'
        "<script async defer crossorigin=\"anonymous\" "
        'src="https://connect.facebook.net/vi_VN/sdk.js#xfbml=1&version=v18.0"></script>'
        f'<div class="fb-customerchat" page_id="{pid}" attribution="setup_tool"></div>'
    )
    return [("body_close", snippet)]


def expand_tiktok_pixel(pixel_id: str) -> List[PlacementHtml]:
    """TikTok Pixel base code — ID trong ttq.load (Events Manager → Web Pixel)."""
    pid = (pixel_id or "").strip()
    if not pid or not re.match(r"^[A-Za-z0-9_-]+$", pid):
        return []
    escaped_js = json.dumps(pid)

    bootstrap = (
        "w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["
        '"page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie"'
        '],ttq.setAndDefer=function(t,e){t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}};'
        "for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);"
        "ttq.instance=function(t){for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e}"
        ',ttq.load=function(e,n){var i="https://analytics.tiktok.com/i18n/pixel/events.js";ttq._i=ttq._i||{},ttq._i[e]=[],ttq._i[e]._u=i,ttq._t=ttq._t||{},ttq._t[e]=+new Date,ttq._o=ttq._o||{},ttq._o[e]=n||{};var o=document.createElement("script");o.type="text/javascript",o.async=!0,o.src=i+"?sdkid="+e+"&lib="+t;var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(o,a)};'
        f"ttq.load({escaped_js});ttq.page();"
    )

    snippet = (
        '<script>'
        "\n"
        "!function (w,d,t) {"
        f"{bootstrap}"
        "}(window, document, 'ttq');"
        "\n</script>"
    )
    return [("head", snippet)]


def expand_zalo_widget(oaid: str) -> List[PlacementHtml]:
    oid = re.sub(r"[^\d]", "", (oaid or "").strip())
    if not oid:
        return []
    snippet = (
        f'<div class="zalo-chat-widget" data-oaid="{oid}" '
        'data-welcome-message="Xin chào! Chúng tôi có thể giúp gì cho bạn?" '
        'data-autopopup="0"></div>'
        '<script src="https://sp.zalo.me/plugins/sdk.js"></script>'
    )
    return [("body_close", snippet)]


def expand_row(row: SiteEmbedCode) -> List[PlacementHtml]:
    """
    Trả về danh sách (placement, html). Một dòng có thể tách thành nhiều fragment (vd: GTM head + body).
    """
    cat = (row.category or "").strip().lower()
    if cat in INTERNAL_ONLY_CATEGORIES:
        return []

    plat = (row.platform or "").lower().strip()
    raw = (row.content or "").strip()

    # Dán full code — giữ một fragment theo đúng placement trong DB
    if raw and looks_like_pasted_html(raw):
        return [(_pla(row), raw)]

    if not raw:
        return []

    if plat == "google":
        if cat == "ga4":
            return expand_ga4(raw)
        if cat == "gtm":
            return expand_gtm(raw)
        if cat == "ads":
            return expand_google_ads_aw(raw)
        if cat == "search_console":
            return expand_google_site_verification(raw)
        if cat == "merchant_center":
            return expand_google_merchant_center_verification(raw)
        # other: chỉ nhận literal HTML (đã xử lý ở trên); không thì bỏ qua token thuần
        return []

    if plat == "facebook":
        if cat == "pixel":
            return expand_facebook_pixel(raw)
        if cat == "domain":
            return expand_facebook_domain_verification(raw)
        if cat == "chat":
            return expand_facebook_chat_page_id(raw)
        return []

    if plat == "zalo":
        if cat == "chat":
            return expand_zalo_widget(raw)
        return []

    if plat == "tiktok":
        if cat == "pixel":
            return expand_tiktok_pixel(raw)
        return []

    if plat == "nanoai":
        # Widget/chat NanoAI — dán nguyên script/snippet từ bảng điều khiển (vị trí theo placement trong DB).
        if raw:
            return [(_pla(row), raw)]
        return []

    if plat == "other":
        if looks_like_pasted_html(raw):
            return [(_pla(row), raw)]
        return []

    return []


def collect_expanded_fragments(rows: Sequence[SiteEmbedCode]) -> Tuple[List[str], List[str], List[str]]:
    head: List[str] = []
    body_open: List[str] = []
    body_close: List[str] = []

    def push(pla: str, fragment: str) -> None:
        f = (fragment or "").strip()
        if not f:
            return
        if pla == "head":
            head.append(f)
        elif pla == "body_open":
            body_open.append(f)
        else:
            body_close.append(f)

    for row in rows:
        if not row.is_active:
            continue
        cat = (row.category or "").strip().lower()
        if cat in INTERNAL_ONLY_CATEGORIES:
            continue
        for pla, fragment in expand_row(row):
            push(pla, fragment)

    return head, body_open, body_close
