"""
Chuẩn hoá URL trong batch Excel theo **trang cần mở** (CSSBuy / Vipomall / PandaMall / 1688).

Dùng kèm form `fetch_target` trên endpoint `batch-from-excel`.
`auto` = quy đổi sang Vipomall khi có thể.
Removed platform tokens are rejected via ``is_removed_import_source_token``.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from app.services.import_1688_scraper import canonical_1688_offer_pc_url, extract_offer_id
from app.services.import_cssbuy_client import (
    canonical_cssbuy_item_url,
    cssbuy_item_page_to_item_slug,
    item_slug_to_cssbuy_item_url,
    is_cssbuy_item_url,
    parse_cssbuy_goods_detail,
)
from app.services.import_source_ids import (
    extract_abb_offer_digits,
    extract_legacy_mirror_slug,
    extract_taobao_tmall_item_id,
    is_legacy_mirror_url,
    is_legacy_placeholder_slug,
    is_removed_import_source_token,
    normalize_product_import_url,
    parse_t_prefixed_item_id,
    removed_source_reject_message,
)
from app.services.import_pandamall_scraper import (
    build_pandamall_1688_pdp_url,
    build_pandamall_taobao_pdp_url,
    is_pandamall_import_url,
    pandamall_canonical_import_url,
    resolve_pandamall_import_url,
)
from app.services.import_vipomall_scraper import is_vipomall_import_url, resolve_vipomall_import_url, vipomall_canonical_import_url
from app.services.vipomall_source_stock import build_vipomall_1688_pdp_url, build_vipomall_taobao_pdp_url

FETCH_TARGET_AUTO = "auto"
FETCH_TARGET_1688 = "1688"
FETCH_TARGET_CSSBUY = "cssbuy"
FETCH_TARGET_VIPOMALL = "vipomall"
FETCH_TARGET_PANDAMALL = "pandamall"
_REJECTED_REMOVED = "removed"


def normalize_fetch_target_param(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    if s in {"", "auto", "automatic"}:
        return FETCH_TARGET_AUTO
    if is_removed_import_source_token(s):
        return _REJECTED_REMOVED
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
    * `fetch_target`: `auto` / `1688` / `cssbuy` / `vipomall` / `pandamall` (đã normalize).
      `auto` = quy về Vipomall. Removed platform tokens → lỗi.
    """
    ft = (fetch_target or FETCH_TARGET_AUTO).strip().lower()
    norm = normalize_product_import_url((raw_url or "").strip())
    if not norm:
        return "", "thiếu hoặc không đọc được URL."

    if ft == _REJECTED_REMOVED or is_removed_import_source_token(ft):
        return norm, removed_source_reject_message(kind="fetch_target")

    if ft == FETCH_TARGET_AUTO:
        return coerce_url_for_excel_batch_import(norm, FETCH_TARGET_VIPOMALL)

    if ft == FETCH_TARGET_CSSBUY:
        if is_cssbuy_item_url(norm):
            return canonical_cssbuy_item_url(norm), None

        gd = parse_cssbuy_goods_detail(norm)
        if gd:
            typ, iid = gd
            if typ == "1688":
                return f"https://www.cssbuy.com/item-1688-{iid}.html", None
            return f"https://www.cssbuy.com/item-{iid}.html", None

        slug_try = extract_legacy_mirror_slug(norm)
        if slug_try and not is_legacy_placeholder_slug(slug_try):
            u = item_slug_to_cssbuy_item_url(slug_try)
            if u:
                return u, None
            return norm, "slug legacy không chuyển được sang URL trang item CSSBuy."

        if is_legacy_mirror_url(norm):
            slug2 = extract_legacy_mirror_slug(norm)
            u2 = item_slug_to_cssbuy_item_url(slug2 or "")
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
            "không quy đổi được sang CSSBuy — cần link 1688 (offer), Taobao/Tmall (id SP), URL item cssbuy.com, hoặc goodsDetail?type=&id=.",
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

        gd = parse_cssbuy_goods_detail(norm)
        if gd:
            typ, iid = gd
            if typ == "1688":
                return build_vipomall_1688_pdp_url(iid), None
            return build_vipomall_taobao_pdp_url(iid), None

        cs_slug = cssbuy_item_page_to_item_slug(norm)
        if cs_slug:
            abb = extract_abb_offer_digits(cs_slug)
            if abb:
                return build_vipomall_1688_pdp_url(abb), None
            if cs_slug.isdigit():
                return build_vipomall_taobao_pdp_url(cs_slug), None

        slug = extract_legacy_mirror_slug(norm)
        if slug and not is_legacy_placeholder_slug(slug):
            abb = extract_abb_offer_digits(slug)
            if abb:
                return build_vipomall_1688_pdp_url(abb), None
            if re.fullmatch(r"\d+", slug):
                return build_vipomall_taobao_pdp_url(slug), None
            return (
                norm,
                "link legacy không nhận dạng offer 1688 (abb-*) hoặc id Taobao số — không quy đổi sang Vipomall.",
            )

        tid = _extract_taobao_tmall_item_id(norm)
        if tid:
            return build_vipomall_taobao_pdp_url(tid), None

        return (
            norm,
            "không quy đổi được sang Vipomall — cần link Taobao/Tmall, T{id}, offer 1688, abb-* / số, hoặc vipomall.vn/san-pham/{id}.",
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

        slug = extract_legacy_mirror_slug(norm)
        if slug and not is_legacy_placeholder_slug(slug):
            abb = extract_abb_offer_digits(slug)
            if abb:
                return build_pandamall_1688_pdp_url(abb), None
            if re.fullmatch(r"\d+", slug):
                return build_pandamall_taobao_pdp_url(slug), None
            return (
                norm,
                "link legacy không nhận dạng offer 1688 (abb-*) hoặc id Taobao số — không quy đổi sang PandaMall.",
            )

        tid = _extract_taobao_tmall_item_id(norm) or parse_t_prefixed_item_id(norm)
        if tid:
            return build_pandamall_taobao_pdp_url(tid), None

        return (
            norm,
            "không quy đổi được sang PandaMall — cần link Taobao/Tmall, T{id}, offer 1688, abb-* / số, hoặc pandamall.vn/taobao|1688/detail/{id}.",
        )

    if ft == FETCH_TARGET_1688:
        oid_direct = extract_offer_id(norm)
        if oid_direct and oid_direct.isdigit():
            u = canonical_1688_offer_pc_url(oid_direct)
            return (u, None) if u else (norm, "không tạo được URL 1688 từ offer id.")

        slug = extract_legacy_mirror_slug(norm)
        if slug and not is_legacy_placeholder_slug(slug):
            abb = extract_abb_offer_digits(slug)
            if abb:
                u = canonical_1688_offer_pc_url(abb)
                return (u, None) if u else (norm, "không tạo được URL 1688 từ slug abb-*.")

            return (
                norm,
                "link chỉ khớp Taobao (/v/<số>) — không quy đổi sang trang chi tiết 1688.",
            )

        if _extract_taobao_tmall_item_id(norm):
            return (
                norm,
                "link Taobao/Tmall — không quy đổi sang trang chi tiết 1688; chọn Vipomall hoặc dùng link 1688/abb-…",
            )

        return (
            norm,
            "không quy đổi được sang 1688 — cần link offer 1688 hoặc slug dạng abb-<số>.",
        )

    return norm, None
