"""
Loại năm sản xuất / năm ra mắt khỏi tên, mô tả và product_info tiếng Việt (listing web).

Giữ nguyên `chinese_name` — admin vẫn đối chiếu tiêu đề NCC.
"""
from __future__ import annotations

import re
from typing import Any, Dict

_YEAR = r"(?:19|20)\d{2}"

_COMPOUND_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in (
        rf"{_YEAR}\s*年\s*(?:春|夏|秋|冬)?(?:季)?(?:新)?(?:款|品|货)?",
        rf"(?:春|夏|秋|冬)(?:季)?\s*{_YEAR}\s*(?:新)?(?:款|品|货)?",
        rf"{_YEAR}\s*(?:春|夏|秋|冬)(?:季)?(?:新)?(?:款|品|货)?",
        rf"{_YEAR}\s*(?:新款|新品|新货|new\s*arrival|collection|spring|summer|autumn|fall|winter)\b",
        rf"(?:新款|新品|new\s*arrival|NEW)\s*{_YEAR}\b",
        rf"(?:hàng|model|collection|xuất\s*xưởng|ra\s*mắt|sản\s*xuất)\s*(?:năm\s*)?{_YEAR}\b",
        rf"\bnăm\s*(?:sản\s*xuất|ra\s*mắt|sx)\s*{_YEAR}?\b",
        rf"\b{_YEAR}\s*(?:款|年)\b",
        rf"\bnăm\s+{_YEAR}\b",
        rf"\bmodel\s+{_YEAR}\b",
        rf"\b{_YEAR}\s+mới\b",
        rf"\bmới\s+{_YEAR}\b",
        rf"\bcollection\s+{_YEAR}\b",
        rf"\b{_YEAR}\s+collection\b",
        rf"\brelease\s+{_YEAR}\b",
        rf"\b{_YEAR}\s+release\b",
    )
)

_STANDALONE_YEAR = re.compile(rf"\b{_YEAR}\b")

_TAXONOMY_VI_KEYS = (
    "khach_hang",
    "ten_tieng_viet",
    "chat_lieu_vi",
    "mo_ta_vi",
    "thuong_hieu_vi",
    "xuat_xu_vi",
    "phong_cach_vi",
    "dip_vi",
    "trong_luong_vi",
    "chieu_cao_got_vi",
    "thong_so_kich_thuoc_vi",
)

LISTING_NO_YEAR_PROMPT_VI = """
NĂM / THỜI GIAN (bắt buộc):
- KHÔNG ghi năm sản xuất, năm ra mắt, «model 20xx», «hàng 20xx», «năm 20xx», «202x collection/mới» trong ten_tieng_viet, mo_ta_vi, khach_hang, phong_cach_vi, dip_vi, thong_so_kich_thuoc_vi và mọi trường tiếng Việt.
- Cụm marketing nguồn (vd. «2026新款», «春季新款», «NEW 2025») → diễn đạt «kiểu mới», «phong cách hiện đại», «mùa xuân/hè/thu/đông» — KHÔNG kèm số năm.
- Giữ số đo kỹ thuật (cm, mm, kg, size) — không nhầm với năm.
"""


def _collapse_ws(text: str) -> str:
    t = re.sub(r"[ \t]+\n", "\n", text)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"  +", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t.strip(" ,.;·|—-")


def strip_listing_year_marketing(text: str, *, remove_standalone_years: bool = True) -> str:
    """Bỏ cụm năm marketing; tùy chọn bỏ mọi năm 19xx–20xx đứng riêng (có khoảng trắng)."""
    if not text or not str(text).strip():
        return ""
    t = str(text)
    for rx in _COMPOUND_RES:
        t = rx.sub("", t)
    if remove_standalone_years:
        t = _STANDALONE_YEAR.sub("", t)
    t = re.sub(r"\b(?:新款|新品|new\s*arrival|NEW)\b", "", t, flags=re.IGNORECASE)
    return _collapse_ws(t)


def sanitize_listing_context_for_ai(text: str) -> str:
    """Ngữ cảnh đưa vào prompt AI — bỏ năm marketing."""
    return strip_listing_year_marketing(text, remove_standalone_years=True)


def sanitize_vi_listing_field(text: str) -> str:
    """Trường tiếng Việt hiển thị web."""
    return strip_listing_year_marketing(text, remove_standalone_years=True)


def sanitize_taxonomy_vi_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in _TAXONOMY_VI_KEYS:
        if key in data and data[key] is not None:
            data[key] = sanitize_vi_listing_field(str(data[key]))
    return data


def apply_listing_year_sanitize_to_product_data(product_data: Dict[str, Any]) -> None:
    """In-place: làm sạch trường hiển thị Việt — không đụng chinese_name."""
    limits = {"name": 500, "description": 20000, "material": 500, "style": 500, "occasion": 500, "features": 2000}
    for key, max_len in limits.items():
        if key in product_data and product_data[key]:
            cleaned = sanitize_vi_listing_field(str(product_data[key]))
            if cleaned:
                product_data[key] = cleaned[:max_len]

    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return

    inner = pi.get("product_info")
    if isinstance(inner, dict):
        for key in ("name", "material_vi", "target_audience_suggestion_vi", "brand", "origin"):
            if inner.get(key):
                inner[key] = sanitize_vi_listing_field(str(inner[key]))[:500]

    spec = pi.get("specifications")
    if isinstance(spec, dict):
        for key in ("style", "occasion", "upper_material"):
            if spec.get(key):
                spec[key] = sanitize_vi_listing_field(str(spec[key]))[:500]

    meta = pi.get("import_taxonomy_meta")
    if isinstance(meta, dict) and meta.get("khach_hang_vi"):
        meta["khach_hang_vi"] = sanitize_vi_listing_field(str(meta["khach_hang_vi"]))[:500]
