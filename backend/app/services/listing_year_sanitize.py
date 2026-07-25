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

_CJK_CHINA_STYLE_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"国风(?:元素|系列|款)?",
        r"国潮(?:风|元素|系列|款)?",
        r"新国潮",
        r"新中式",
        r"中国风(?:元素|系列|款)?",
        r"中式(?:风|美学|元素|复古|系列|款)?",
        r"汉风",
        r"汉服(?:风|款|系|元素)?",
        r"汉元素",
        r"古风",
        r"唐(?:装|风|式)",
        r"民国风?",
        r"宫廷风?",
        r"禅(?:意|风|韵)",
        r"东方(?:风|美学|元素|韵味)?",
        r"国粹",
        r"华夏(?:风|元素)?",
        r"中国(?:风|元素|传统)",
        r"复古国风",
        r"水墨风?",
        r"武侠风?",
    )
)

_VI_CHINA_STYLE_RES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in (
        r"phong\s*cách\s*quốc\s*gia",
        r"phong\s*cách\s*trung\s*quốc",
        r"phong\s*cách\s*trung\s*hoa",
        r"phong\s*cách\s*hán(?:\s*quốc|\s*phục)?",
        r"phong\s*cách\s*tân\s*trung(?:\s*thức)?",
        r"phong\s*cách\s*cổ\s*(?:phong|điển)(?:\s*trung(?:\s*hoa|\s*quốc)?)?",
        r"phong\s*cách\s*đông\s*phương",
        r"phong\s*cách\s*cung\s*đình",
        r"phong\s*cách\s*dân\s*quốc",
        r"phong\s*cách\s*thiền(?:\s*ý|\s*phong)?",
        r"phong\s*cách\s*thủy\s*mặc",
        r"phong\s*cách\s*võ\s*hiệp",
        r"phong\s*cách\s*hán\s*phục",
        r"kiểu\s*hán\s*phục",
        r"quốc\s*phong",
        r"tân\s*trung\s*thức",
        r"trung\s*thức",
        r"kiểu\s*trung(?:\s*quốc|\s*hoa)?",
        r"thẩm\s*mỹ\s*đông\s*phương",
        r"hoa\s*hạ",
        r"quốc\s*túy",
        r"\bguofeng\b",
        r"\bguochao\b",
        r"\bhanfu\b",
    )
)

LISTING_NO_CHINESE_STYLE_PROMPT_VI = """
PHONG CÁCH / MARKETING TRUNG QUỐC (bắt buộc):
- Cụm nguồn liên quan phong cách Trung Quốc (vd. 国风, 国潮, 新中式, 中国风, 中式, 汉风, 汉服, 古风, 唐装, 民国风, 宫廷风, 禅意, 东方美学, 国粹, 华夏, 水墨风, 武侠风…) KHÔNG dịch sang tiếng Việt — BỎ HẲN khỏi ten_tieng_viet, mo_ta_vi và phong_cach_vi.
- Không ghi bản dịch kiểu «phong cách quốc gia/Trung Quốc/Trung Hoa», «tân trung thức», «quốc phong», «phong cách đông phương», «Hán phục», «cung đình», «thiền ý»…
- Giữ mô tả sản phẩm thực tế (váy, thắt eo, không tay, chất liệu, form…); chỉ loại cụm marketing phong cách Trung.
- Vẫn được ghi xuất xứ «Trung Quốc» ở xuat_xu_vi khi có thông tin thật; vẫn dùng phong cách cụ thể khác (vd. «công sở», «casual», «thể thao»).
"""

LISTING_SANITIZE_PROMPT_VI = LISTING_NO_YEAR_PROMPT_VI + LISTING_NO_CHINESE_STYLE_PROMPT_VI


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


def strip_listing_chinese_style_marketing(text: str) -> str:
    """Bỏ cụm marketing phong cách Trung Quốc (nguồn CJK hoặc bản dịch Việt)."""
    if not text or not str(text).strip():
        return ""
    t = str(text)
    for rx in _CJK_CHINA_STYLE_RES:
        t = rx.sub("", t)
    for rx in _VI_CHINA_STYLE_RES:
        t = rx.sub("", t)
    return _collapse_ws(t)


def sanitize_listing_context_for_ai(text: str) -> str:
    """Ngữ cảnh đưa vào prompt AI — bỏ năm marketing và cụm quốc phong."""
    t = strip_listing_year_marketing(text, remove_standalone_years=True)
    return strip_listing_chinese_style_marketing(t)


def sanitize_vi_listing_field(text: str) -> str:
    """Trường tiếng Việt hiển thị web."""
    t = strip_listing_year_marketing(text, remove_standalone_years=True)
    return strip_listing_chinese_style_marketing(t)


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
