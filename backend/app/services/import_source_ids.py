"""
Shared import ID / URL helpers used by Vipomall, CSSBuy, PandaMall, 1688, and stock checks.

Legacy catalog continuity: old rows may still store mirror host URLs or product_id
prefixes from a removed import platform. All such host/prefix literals live HERE only;
other modules call the helpers below — do not hardcode those strings elsewhere.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, quote, urlparse

# --- Legacy mirror host / id literals (single concentration point) ---
_LEGACY_MIRROR_HOST_PRIMARY = "hibox.mn"
_LEGACY_MIRROR_HOST_KZ = "taobao1688.kz"
_LEGACY_PRODUCT_ID_PREFIX = "hibox_"
_LEGACY_PLACEHOLDER_SLUG = "hibox_import"
_LEGACY_DRAFT_SOURCE = "hibox"
_REMOVED_SOURCE_ALIASES = frozenset({"hibox", "hi-box", "hi_box", "hibox_mn"})

# Legacy product_info / market_info keys still present on old drafts (read-only).
LEGACY_PRODUCT_INFO_SPEC_KEYS: Tuple[str, ...] = (
    "supplier_specs_excerpt",
    "hibox_specs_excerpt",
)
LEGACY_MARKET_INFO_KEYS: Tuple[str, ...] = (
    "hibox_display_mnt_integer",
    "hibox_mnt_per_cny_used",
)

_STRIP_INVISIBLE_PREFIX = re.compile(r"^[\ufeff\u200b\u200c\u200d\u2060\s]+")

# Legacy absolute …/v/<slug> on historical mirror hosts (DB matching / paste normalize).
_LEGACY_MIRROR_ABS_V_RE = re.compile(
    rf"(?i)\bhttps?://(?:[a-z0-9][a-z0-9.-]*\.)*{re.escape(_LEGACY_MIRROR_HOST_PRIMARY)}"
    r"(?::\d+)?(?:/[a-z]{2,5})?/v/([^\s/?#\"'<>()\]]+)",
)
_BARE_LEGACY_MIRROR_V_RE = re.compile(
    rf"(?i)\b(?:www\.)?(?:[a-z0-9][a-z0-9.-]*\.)*{re.escape(_LEGACY_MIRROR_HOST_PRIMARY)}"
    r"(?::\d+)?(?:/[a-z]{2,5})?/v/([^\s/?#\"'<>()\]]+)",
)
_TAOBAO1688_KZ_HOST_RE = re.compile(
    rf"^(?:www\.)?{re.escape(_LEGACY_MIRROR_HOST_KZ)}$", re.I
)
_MIRROR_ITEM_ID_RE = re.compile(r"^[a-zA-Z0-9][\w.-]{1,220}$")
_CANONICAL_TAOBAO_ITEM_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,220}$")
_T_PREFIX_ITEM_RE = re.compile(r"^[Tt](\d{5,})$")
_TAOBAO_TMAIL_HOST_RE = re.compile(r"(?:^|\.)taobao\.com$|(?:^|\.)tmall\.com$", re.I)
_ABB_1688_OFFER_RE = re.compile(r"(?i)^abb-(\d+)$")


def is_removed_import_source_token(raw: Optional[str]) -> bool:
    """True when caller passed a removed platform token (normalize aliases)."""
    s = (raw or "").strip().lower()
    return s in _REMOVED_SOURCE_ALIASES


def normalize_removed_source_token(raw: Optional[str]) -> Optional[str]:
    """Return canonical removed-source token or None."""
    if is_removed_import_source_token(raw):
        return _LEGACY_DRAFT_SOURCE
    return None


def removed_source_reject_message(*, kind: str = "source") -> str:
    """User-facing reject copy without platform branding."""
    k = (kind or "source").strip().lower()
    if k == "fetch_target":
        return "fetch_target này đã gỡ — chọn auto/vipomall/cssbuy/pandamall."
    if k == "domain":
        return "domain này đã gỡ — dùng cssbuy hoặc vipomall."
    return "Nguồn import đã gỡ — dùng Vipomall / PandaMall / CSSBuy (hoặc auto)."


def legacy_draft_source_name() -> str:
    """Historical draft.source value still present in DB."""
    return _LEGACY_DRAFT_SOURCE


def is_legacy_placeholder_slug(slug: Optional[str]) -> bool:
    s = (slug or "").strip()
    return (not s) or s.lower() == _LEGACY_PLACEHOLDER_SLUG


def legacy_product_id_prefix() -> str:
    return _LEGACY_PRODUCT_ID_PREFIX


def is_legacy_mirror_product_id(product_id: Optional[str]) -> bool:
    pid = (product_id or "").strip()
    return pid.startswith(_LEGACY_PRODUCT_ID_PREFIX)


def legacy_product_id_for_slug(slug: str) -> str:
    """Build historical product_id placeholder ``{prefix}{slug}`` for DB matching."""
    return f"{_LEGACY_PRODUCT_ID_PREFIX}{(slug or '').strip()}"


def legacy_mirror_cookie_seed_urls() -> Dict[str, str]:
    """Playwright cookie seed origins for old cookie exports (if still on disk)."""
    return {
        _LEGACY_MIRROR_HOST_PRIMARY: f"https://{_LEGACY_MIRROR_HOST_PRIMARY}/",
        _LEGACY_MIRROR_HOST_KZ: f"https://{_LEGACY_MIRROR_HOST_KZ}/",
    }


def legacy_mirror_cookie_hosts() -> frozenset[str]:
    return frozenset({_LEGACY_MIRROR_HOST_PRIMARY, _LEGACY_MIRROR_HOST_KZ})


def legacy_mirror_link_markers() -> Tuple[str, ...]:
    """Substrings suitable for ``marker in url.lower()`` eligibility checks."""
    return (_LEGACY_MIRROR_HOST_PRIMARY, _LEGACY_MIRROR_HOST_KZ)


def legacy_mirror_link_ilike_patterns() -> Tuple[str, ...]:
    """SQLAlchemy ``ilike`` patterns for Product.link_default legacy hosts."""
    return (f"%{_LEGACY_MIRROR_HOST_PRIMARY}%", f"%{_LEGACY_MIRROR_HOST_KZ}%")


def legacy_mirror_v_path_ilike_pattern(slug: str) -> str:
    """ILIKE pattern matching ``…/{host}/v/{slug}…`` on link_default."""
    s = (slug or "").strip()
    return f"%{_LEGACY_MIRROR_HOST_PRIMARY}%/v/{s}%"


def parse_t_prefixed_item_id(raw: str) -> Optional[str]:
    """Internal code T801751959231 → 801751959231."""
    s = (raw or "").strip()
    m = _T_PREFIX_ITEM_RE.match(s)
    return m.group(1) if m else None


def normalize_product_import_url(raw: str) -> str:
    """Normalize pasted URLs: sentence-wrapped, markdown, missing https, etc."""
    s = (raw or "").strip()
    if not s:
        return ""
    s = _STRIP_INVISIBLE_PREFIX.sub("", s)
    s = re.sub(r"[\ufeff\u200b-\u200d\u2060]", "", s)
    if not s.strip():
        return ""
    s = s.strip()

    m_http = re.search(r"\bhttps?://[^\s\]\)<>\'\"]+", s, flags=re.I)
    if m_http:
        s = m_http.group(0).rstrip(".,;:\"'”’)]}")
    else:
        m_bare = _BARE_LEGACY_MIRROR_V_RE.search(s)
        if m_bare:
            start = m_bare.start()
            frag = s[start : m_bare.end()]
            if not frag.lower().startswith(("http://", "https://")):
                s = f"https://{frag.lstrip('/')}"
            else:
                s = frag

    s = s.strip().strip('"').strip("'").strip("\u201c").strip("\u201d").strip(">").strip("<")
    if s.lower().startswith("//"):
        return f"https:{s}"
    if not re.match(r"^[a-z][a-z0-9+.-]*:", s, re.I):
        return f"https://{s.lstrip('/')}"
    return s


def extract_taobao_tmall_item_id(url: str) -> Optional[str]:
    """Extract item id from taobao.com / tmall.com (?id= / item_id)."""
    norm = normalize_product_import_url((url or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    host = (p.hostname or "").lower().replace("www.", "")
    if not _TAOBAO_TMAIL_HOST_RE.search(host):
        return None
    qs = parse_qs(p.query or "")
    for key in ("id", "item_id", "itemId"):
        for val in qs.get(key) or []:
            s = (val or "").strip()
            if s.isdigit():
                return s
    return None


def extract_abb_offer_digits(slug: str) -> Optional[str]:
    """«abb-922386436529» → «922386436529»; other slugs → None."""
    m = _ABB_1688_OFFER_RE.match((slug or "").strip())
    return m.group(1) if m else None


def abb_slug_is_1688_offer(slug: str) -> bool:
    return extract_abb_offer_digits(slug) is not None


def supply_product_link_default_for_item_slug(slug: str) -> str:
    """
    Supplier detail URL for link_default / product_url.
    abb-<digits> → 1688 detail; otherwise → Tmall item.htm?id=….
    """
    oid = extract_abb_offer_digits(slug)
    if oid:
        return f"https://detail.1688.com/offer/{oid}.html"
    tid = (slug or "").strip()
    if not tid:
        return ""
    return f"https://detail.tmall.com/item.htm?id={quote(tid, safe='')}"


def build_canonical_taobao_product_id(item_id: str, sku_code: str = "") -> str:
    """Canonical Taobao product_id: T + item id (e.g. T797317200783)."""
    del sku_code  # reserved for callers that still pass sku
    tid = str(item_id or "").strip()
    if not tid:
        raise ValueError("thiếu mã item Taobao (slug / id).")
    if not _CANONICAL_TAOBAO_ITEM_RE.fullmatch(tid):
        raise ValueError(f"mã item Taobao không hợp lệ: {tid!r}")
    return f"T{tid}"


def build_canonical_product_id_from_item_slug(slug: str, sku_code: str = "") -> str:
    """
    Publish product_id from an item slug:
    - abb-<digits> → A<digits> (1688)
    - otherwise → T<slug> (Taobao)
    """
    hid = (slug or "").strip()
    oid = extract_abb_offer_digits(hid)
    if oid:
        if not oid.isdigit():
            raise ValueError("offer id 1688 (sau abb-) phải là chữ số.")
        return f"A{oid}"
    return build_canonical_taobao_product_id(hid, sku_code)


def canonicalize_legacy_placeholder_product_id(product_data: Dict[str, Any]) -> None:
    """
    Legacy drafts may still have product_id = «{prefix}<slug>».
    Convert to A<id1688> or T<id> — no-op if not that prefix.
    """
    pid = (product_data.get("product_id") or "").strip()
    if not is_legacy_mirror_product_id(pid):
        return
    slug = pid[len(_LEGACY_PRODUCT_ID_PREFIX) :].strip()
    if is_legacy_placeholder_slug(slug):
        return
    try:
        product_data["product_id"] = build_canonical_product_id_from_item_slug(slug)
    except ValueError:
        pass


def _taobao1688_kz_hostname_ok(hostname: Optional[str]) -> bool:
    if not hostname:
        return False
    return bool(_TAOBAO1688_KZ_HOST_RE.fullmatch(str(hostname).strip().lower()))


def extract_taobao1688_kz_item_id(url: str) -> Optional[str]:
    """Legacy mirror: https://taobao1688.kz/item?id=abb-… → abb-…"""
    norm = normalize_product_import_url((url or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    if not _taobao1688_kz_hostname_ok(p.hostname):
        return None
    qs = parse_qs(p.query)
    for key in ("id", "item_id", "itemId"):
        for v in qs.get(key) or []:
            raw_v = (v or "").strip()
            if raw_v and _MIRROR_ITEM_ID_RE.match(raw_v):
                return raw_v
    return None


def _legacy_mirror_hostname_ok(hostname: Optional[str]) -> bool:
    """Only real *.{primary host} — reject evil{host} style hosts."""
    if not hostname:
        return False
    h = str(hostname).lower().rstrip(".")
    return bool(re.fullmatch(rf"(?:[\w-]+\.)*{re.escape(_LEGACY_MIRROR_HOST_PRIMARY)}", h))


def _slug_from_v_path(path: str) -> Optional[str]:
    """`/v/slug`, `/locale/v/slug`, or `/v/cat/slug` — last segment after `/v/`."""
    if not path:
        return None
    low = path.lower()
    i = low.rfind("/v/")
    if i < 0:
        return None
    rest = path[i + len("/v/") :].strip("/")
    if not rest:
        return None
    slug = rest.split("/")[-1].strip()
    return slug or None


def extract_legacy_mirror_slug(url: str) -> Optional[str]:
    """
    Resolve item slug from legacy mirror URLs still present in DB / drafts.
    Not used for scraping.
    """
    raw = normalize_product_import_url((url or "").strip())
    if not raw:
        return None

    parsed = urlparse(raw)
    if _legacy_mirror_hostname_ok(parsed.hostname):
        slug = _slug_from_v_path(parsed.path or "")
        if slug:
            return slug

    m = _LEGACY_MIRROR_ABS_V_RE.search(raw)
    if m:
        seg = (m.group(1) or "").strip("/").strip()
        if seg:
            return seg.split("/")[-1].strip()

    kz = extract_taobao1688_kz_item_id(raw)
    if kz:
        return kz

    return None


def is_legacy_mirror_url(raw: str) -> bool:
    """True for legacy primary-mirror / taobao1688.kz item URLs (matching only)."""
    norm = normalize_product_import_url(raw or "")
    if not norm:
        return False
    try:
        p = urlparse(norm)
    except ValueError:
        return False
    if _legacy_mirror_hostname_ok(p.hostname):
        return True
    return extract_taobao1688_kz_item_id(norm) is not None


def first_legacy_spec_excerpt(spec: Dict[str, Any]) -> str:
    """Read first non-empty legacy/supplier specs excerpt from product_info blob."""
    if not isinstance(spec, dict):
        return ""
    for key in LEGACY_PRODUCT_INFO_SPEC_KEYS:
        val = spec.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def market_info_has_legacy_mnt_footprint(market_info: Dict[str, Any]) -> bool:
    """True when old listing footprint keys are present on market_info."""
    if not isinstance(market_info, dict):
        return False
    return any(market_info.get(k) is not None for k in LEGACY_MARKET_INFO_KEYS)


def remap_legacy_import_source(source: Optional[str]) -> str:
    """Map removed draft source token → vipomall (silent)."""
    s = (source or "").strip().lower()
    if is_removed_import_source_token(s) or s == _LEGACY_DRAFT_SOURCE:
        return "vipomall"
    return s or "vipomall"
