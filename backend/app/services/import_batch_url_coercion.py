"""
Chuẩn hoá URL trong batch Excel theo **trang cần mở** (Hibox vs CSSBuy vs 1688 trực tiếp).

Dùng kèm form `fetch_target` trên endpoint `batch-from-excel`.
`auto` = quy đổi sang Hibox khi có thể (Taobao/Tmall → /v/<id>, offer 1688 → /v/abb-<id>, v.v.) vì import chỉ scrape qua Hibox.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.services.import_1688_scraper import canonical_1688_offer_pc_url, extract_offer_id
from app.services.import_cssbuy_client import (
    canonical_cssbuy_item_url,
    hibox_slug_to_cssbuy_item_url,
    is_cssbuy_item_url,
)
from app.services.import_hibox_scraper import (
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    extract_taobao_tmall_item_id,
    hibox_canonical_scrape_url,
    is_hibox_import_url,
    normalize_product_import_url,
    parse_t_prefixed_item_id,
)
from app.services.import_pandamall_scraper import (
    build_pandamall_1688_pdp_url,
    build_pandamall_taobao_pdp_url,
    extract_pandamall_detail,
    is_pandamall_import_url,
    pandamall_canonical_import_url,
    resolve_pandamall_import_url,
)
from app.services.import_vipomall_scraper import is_vipomall_import_url, resolve_vipomall_import_url, vipomall_canonical_import_url
from app.services.vipomall_source_stock import build_vipomall_1688_pdp_url, build_vipomall_taobao_pdp_url

FETCH_TARGET_AUTO = "auto"
FETCH_TARGET_HIBOX = "hibox"
FETCH_TARGET_1688 = "1688"
FETCH_TARGET_CSSBUY = "cssbuy"
FETCH_TARGET_VIPOMALL = "vipomall"
FETCH_TARGET_PANDAMALL = "pandamall"


def normalize_fetch_target_param(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    if s in {"", "auto", "automatic"}:
        return FETCH_TARGET_AUTO
    if s in {"hibox", "hi-box", "hi_box", "hibox_mn"}:
        return FETCH_TARGET_HIBOX
    if s in {"cssbuy", "css_buy", "css-buy"}:
        return FETCH_TARGET_CSSBUY
    if s in {"vipomall", "vipo", "vipomail", "vipo_mall", "vipo-mall"}:
        return FETCH_TARGET_VIPOMALL
    if s in {"pandamall", "panda", "panda_mall", "panda-mall"}:
        return FETCH_TARGET_PANDAMALL
    if s in {"1688", "detail_1688", "alibaba_1688"}:
        return FETCH_TARGET_1688
    return FETCH_TARGET_AUTO


def _extract_taobao_tmall_item_id(url: str) -> Optional[str]:
    return extract_taobao_tmall_item_id(url) or parse_t_prefixed_item_id((url or "").strip())


def coerce_url_for_excel_batch_import(
    raw_url: str, fetch_target: str
) -> Tuple[str, Optional[str]]:
    """
    Trả (url_sau_khi_chuẩn, lỗi_skip).

    * `lỗi_skip` khác None → bỏ dòng với thông báo tiếng Việt.
    * `fetch_target` phải là một trong `auto` / `hibox` / `1688` / `cssbuy` / `vipomall` / `pandamall` (đã normalize).
      `auto` = quy về Hibox như `hibox`.
    """
    ft = (fetch_target or FETCH_TARGET_AUTO).strip().lower()
    norm = normalize_product_import_url((raw_url or "").strip())
    if not norm:
        return "", "thiếu hoặc không đọc được URL."

    if ft == FETCH_TARGET_AUTO:
        return coerce_url_for_excel_batch_import(norm, FETCH_TARGET_HIBOX)

    if ft == FETCH_TARGET_HIBOX:
        detail = extract_pandamall_detail(norm) if is_pandamall_import_url(norm) else None
        if detail:
            item_id, platform = detail
            if platform == "1688":
                return f"https://hibox.mn/v/abb-{item_id}", None
            return f"https://hibox.mn/v/{item_id}", None

        if is_vipomall_import_url(norm):
            return vipomall_canonical_import_url(norm), None

        slug_try = extract_hibox_slug(norm)
        if slug_try and slug_try != "hibox_import":
            return hibox_canonical_scrape_url(norm), None
        if is_hibox_import_url(norm):
            return hibox_canonical_scrape_url(norm), None

        oid = extract_offer_id(norm)
        if oid and oid.isdigit():
            return f"https://hibox.mn/v/abb-{oid}", None

        tid = _extract_taobao_tmall_item_id(norm)
        if tid:
            return f"https://hibox.mn/v/{tid}", None

        return (
            norm,
            "không quy đổi được sang Hibox — cần link 1688 (offer), Taobao/Tmall (id SP), hoặc Hibox/taobao1688.kz.",
        )

    if ft == FETCH_TARGET_CSSBUY:
        if is_cssbuy_item_url(norm):
            return canonical_cssbuy_item_url(norm), None

        slug_try = extract_hibox_slug(norm)
        if slug_try and slug_try != "hibox_import":
            u = hibox_slug_to_cssbuy_item_url(slug_try)
            if u:
                return u, None
            return norm, "slug Hibox không chuyển được sang URL trang item CSSBuy."

        if is_hibox_import_url(norm):
            slug2 = extract_hibox_slug(norm)
            u2 = hibox_slug_to_cssbuy_item_url(slug2 or "")
            if u2:
                return u2, None

        oid = extract_offer_id(norm)
        if oid and oid.isdigit():
            return f"https://www.cssbuy.com/item-1688-{oid}.html", None

        tid = _extract_taobao_tmall_item_id(norm)
        if tid:
            return f"https://www.cssbuy.com/item-{tid}.html", None

        return (
            norm,
            "không quy đổi được sang CSSBuy — cần link 1688 (offer), Taobao/Tmall (id SP), Hibox/taobao1688.kz, hoặc URL item cssbuy.com.",
        )

    if ft == FETCH_TARGET_VIPOMALL:
        try:
            url, _pt = resolve_vipomall_import_url(norm)
            return url, None
        except Exception:
            pass
        if is_vipomall_import_url(norm):
            return vipomall_canonical_import_url(norm), None

        oid = extract_offer_id(norm)
        if oid and oid.isdigit():
            return build_vipomall_1688_pdp_url(oid), None

        slug = extract_hibox_slug(norm)
        if slug and slug != "hibox_import":
            abb = extract_hibox_1688_offer_digits(slug)
            if abb:
                return build_vipomall_1688_pdp_url(abb), None
            if re.fullmatch(r"\d+", slug):
                return build_vipomall_taobao_pdp_url(slug), None
            return (
                norm,
                "link Hibox không nhận dạng offer 1688 (abb-*) hoặc id Taobao số — không quy đổi sang Vipomall.",
            )

        tid = _extract_taobao_tmall_item_id(norm)
        if tid:
            return build_vipomall_taobao_pdp_url(tid), None

        return (
            norm,
            "không quy đổi được sang Vipomall — cần link Taobao/Tmall, T{id}, offer 1688, Hibox abb-* / số, hoặc vipomall.vn/san-pham/{id}.",
        )

    if ft == FETCH_TARGET_PANDAMALL:
        tid_early = parse_t_prefixed_item_id((raw_url or "").strip())
        if tid_early:
            return build_pandamall_taobao_pdp_url(tid_early), None

        try:
            url, _platform = resolve_pandamall_import_url(norm)
            return url, None
        except Exception:
            pass
        if is_pandamall_import_url(norm):
            return pandamall_canonical_import_url(norm), None

        oid = extract_offer_id(norm)
        if oid and oid.isdigit():
            return build_pandamall_1688_pdp_url(oid), None

        slug = extract_hibox_slug(norm)
        if slug and slug != "hibox_import":
            abb = extract_hibox_1688_offer_digits(slug)
            if abb:
                return build_pandamall_1688_pdp_url(abb), None
            if re.fullmatch(r"\d+", slug):
                return build_pandamall_taobao_pdp_url(slug), None
            return (
                norm,
                "link Hibox không nhận dạng offer 1688 (abb-*) hoặc id Taobao số — không quy đổi sang PandaMall.",
            )

        tid = _extract_taobao_tmall_item_id(norm) or parse_t_prefixed_item_id(norm)
        if tid:
            return build_pandamall_taobao_pdp_url(tid), None

        return (
            norm,
            "không quy đổi được sang PandaMall — cần link Taobao/Tmall, T{id}, offer 1688, Hibox abb-* / số, hoặc pandamall.vn/taobao|1688/detail/{id}.",
        )

    if ft == FETCH_TARGET_1688:
        oid_direct = extract_offer_id(norm)
        if oid_direct and oid_direct.isdigit():
            u = canonical_1688_offer_pc_url(oid_direct)
            return (u, None) if u else (norm, "không tạo được URL 1688 từ offer id.")

        slug = extract_hibox_slug(norm)
        if slug and slug != "hibox_import":
            abb = extract_hibox_1688_offer_digits(slug)
            if abb:
                u = canonical_1688_offer_pc_url(abb)
                return (u, None) if u else (norm, "không tạo được URL 1688 từ slug abb-*.")

            # slug Taobao (chữ số) — không có offer 1688
            return (
                norm,
                "link chỉ khớp Taobao (Hibox /v/<số>) — không quy đổi sang trang chi tiết 1688.",
            )

        if _extract_taobao_tmall_item_id(norm):
            return (
                norm,
                "link Taobao/Tmall — không quy đổi sang trang chi tiết 1688; chọn «Hibox» hoặc dùng link 1688/abb-…",
            )

        return (
            norm,
            "không quy đổi được sang 1688 — cần link offer 1688 hoặc Hibox dạng abb-<số>.",
        )

    return norm, None
