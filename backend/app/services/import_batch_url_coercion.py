"""
Chuẩn hoá URL trong batch Excel theo **trang cần mở** (Hibox vs 1688 trực tiếp).

Dùng kèm form `fetch_target` trên endpoint `batch-from-excel`; `auto` = giữ hành vi cũ (nhận dạng từ URL).
"""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from app.services.import_1688_scraper import canonical_1688_offer_pc_url, extract_offer_id
from app.services.import_hibox_scraper import (
    extract_hibox_1688_offer_digits,
    extract_hibox_slug,
    hibox_canonical_scrape_url,
    is_hibox_import_url,
    normalize_product_import_url,
)

FETCH_TARGET_AUTO = "auto"
FETCH_TARGET_HIBOX = "hibox"
FETCH_TARGET_1688 = "1688"


def normalize_fetch_target_param(raw: Optional[str]) -> str:
    s = (raw or "").strip().lower()
    if s in {"", "auto", "automatic"}:
        return FETCH_TARGET_AUTO
    if s in {"hibox", "hi-box", "hi_box", "hibox_mn"}:
        return FETCH_TARGET_HIBOX
    if s in {"1688", "detail_1688", "alibaba_1688"}:
        return FETCH_TARGET_1688
    return FETCH_TARGET_AUTO


def _extract_taobao_tmall_item_id(url: str) -> Optional[str]:
    norm = normalize_product_import_url((url or "").strip())
    if not norm:
        return None
    try:
        p = urlparse(norm)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if "taobao.com" not in host and "tmall.com" not in host:
        return None
    qs = parse_qs(p.query)
    for key in ("id", "item_id", "itemId"):
        for v in qs.get(key) or []:
            s = (v or "").strip()
            if s.isdigit():
                return s
    return None


def coerce_url_for_excel_batch_import(
    raw_url: str, fetch_target: str
) -> Tuple[str, Optional[str]]:
    """
    Trả (url_sau_khi_chuẩn, lỗi_skip).

    * `lỗi_skip` khác None → bỏ dòng với thông báo tiếng Việt.
    * `fetch_target` phải là một trong `auto` / `hibox` / `1688` (đã normalize).
    """
    ft = (fetch_target or FETCH_TARGET_AUTO).strip().lower()
    norm = normalize_product_import_url((raw_url or "").strip())
    if not norm:
        return "", "thiếu hoặc không đọc được URL."

    if ft == FETCH_TARGET_AUTO:
        return norm, None

    if ft == FETCH_TARGET_HIBOX:
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
