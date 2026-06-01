"""
Loại token slug marketing không phải thuộc tính SP (mã NCC, thương hiệu lạ: jitde, gutdu…).
"""
from __future__ import annotations

import re
from typing import FrozenSet, Optional, Set, Tuple

from app.utils.vietnamese import remove_vietnamese_accents

# Mã NCC / thương hiệu hay gặp trong URL marketing (slug không dấu).
_KNOWN_VENDOR_SLUG_TOKENS: FrozenSet[str] = frozenset(
    {
        "jitde",
        "gutdu",
        "hibox",
        "taobao",
        "1688",
    }
)

# Segment slug được coi là mô tả SP (loại, mùa, chất liệu, giới tính…).
_FASHION_SLUG_SEGMENTS: FrozenSet[str] = frozenset(
    {
        "ao",
        "quan",
        "vay",
        "dam",
        "giay",
        "dep",
        "tui",
        "xach",
        "khoac",
        "thun",
        "so",
        "mi",
        "som",
        "nam",
        "nu",
        "jean",
        "jogger",
        "kaki",
        "da",
        "bo",
        "vai",
        "bong",
        "ni",
        "cotton",
        "linen",
        "len",
        "long",
        "mua",
        "he",
        "dong",
        "thu",
        "xuan",
        "ha",
        "lun",
        "chat",
        "lieu",
        "cao",
        "cap",
        "the",
        "thao",
        "polo",
        "cardigan",
        "hoodie",
        "sweater",
        "vest",
        "blazer",
        "somi",
        "thun",
        "lot",
        "set",
        "bo",
        "tre",
        "em",
        "be",
        "gai",
        "trai",
        "unisex",
        "co",
        "tron",
        "dai",
        "ngan",
        "rong",
        "om",
        "body",
        "crop",
        "baggy",
        "ong",
        "suong",
        "kaki",
        "cargo",
        "skinny",
        "slim",
        "regular",
        "oversize",
        "basic",
        "thoi",
        "trang",
    }
)

# Marketing / noise — không đưa vào từ khóa tìm kiếm.
_MARKETING_NOISE_SEGMENTS: FrozenSet[str] = frozenset(
    {
        "san",
        "pham",
        "moi",
        "mien",
        "phi",
        "van",
        "chuyen",
        "toan",
        "quoc",
        "hang",
        "sale",
        "hot",
        "free",
        "ship",
        "freeship",
        "km",
        "tang",
        "qua",
        "uu",
        "dai",
        "giam",
        "gia",
        "moi-ma",
        "phong",
        "cach",
        "tre",
        "trung",
        "han",
        "quoc",
        "dep",
        "hieu",
        "chat",
        "luong",
        "cao",
        "re",
        "tot",
        "xin",
        "shop",
        "store",
    }
)

_VENDOR_SLUG_RE = re.compile(r"^[a-z]{4,12}$")


def vendor_slug_tokens_from_path(path: str) -> Set[str]:
    """Token trong URL nghi là mã NCC / thương hiệu (vd jitde)."""
    raw = (path or "").strip().lower().replace("/", "-")
    parts = [p for p in raw.split("-") if p]
    out: Set[str] = set()
    for seg in parts:
        low = seg.lower()
        if low in _KNOWN_VENDOR_SLUG_TOKENS:
            out.add(low)
            continue
        if not _VENDOR_SLUG_RE.match(low):
            continue
        if low in _FASHION_SLUG_SEGMENTS or low in _MARKETING_NOISE_SEGMENTS:
            continue
        if re.match(r"^g0\d", low) or re.match(r"^\d", low):
            continue
        if low in ("moi", "ma", "gia", "san", "pham"):
            continue
        out.add(low)
    return out


def strip_vendor_segments_from_slug(slug: str, source_path: str = "") -> str:
    vendors = vendor_slug_tokens_from_path(source_path or slug)
    if not vendors:
        return (slug or "").strip()
    parts = [p for p in (slug or "").split("-") if p and p.lower() not in vendors]
    return "-".join(parts)


# Chất liệu — không đưa vào từ khóa redirect (tránh AND search quá hẹp).
_MATERIAL_ONLY_WORDS: FrozenSet[str] = frozenset(
    {
        "vai",
        "vải",
        "bong",
        "bông",
        "cotton",
        "linen",
        "polyester",
        "nylon",
        "spandex",
        "voan",
        "lua",
        "lụa",
        "ni",
        "len",
        "lông",
        "poly",
        "mesh",
        "satin",
        "flannel",
        "fleece",
        "det",
        "dệt",
        "chat",
        "lieu",
        "chất",
        "liệu",
    }
)


_FOOTWEAR_SLUG_TYPES: dict[str, str] = {
    "boot": "boot",
    "giay": "giày",
    "dep": "dép",
    "sandal": "sandal",
    "sneaker": "sneaker",
    "loafer": "loafer",
    "chelsea": "chelsea",
}
_HEIGHT_QUERY_MARKERS: Tuple[str, ...] = (
    "cao got",
    "cao gót",
    "de cao",
    "đế cao",
    "co cao",
    "cổ cao",
    "chieu cao",
    "chiều cao",
)


def supplement_footwear_search_keywords(text: str, legacy_path: str) -> str:
    """
    Giày dép: đảm bảo có loại (boot/giày…) và chiều cao nếu slug có chieu-cao / đế / cm.
    """
    q = (text or "").strip()
    path = (legacy_path or "").lower().replace("/", "-")
    if not path:
        return q
    parts = [p for p in path.split("-") if p]

    footwear: Optional[str] = None
    for p in parts:
        if p in _FOOTWEAR_SLUG_TYPES:
            footwear = _FOOTWEAR_SLUG_TYPES[p]
            break

    gender: Optional[str] = None
    if "nu" in parts:
        gender = "nữ"
    elif "nam" in parts:
        gender = "nam"

    has_height = bool(
        "chieu-cao" in path
        or "cao-got" in path
        or "de-cao" in path
        or "co-cao" in path
        or re.search(r"-\d{1,2}cm", path)
    )

    if not footwear and not has_height:
        return q

    q_norm = remove_vietnamese_accents(q).lower()
    if footwear and footwear not in q_norm and "giay" not in q_norm:
        if gender and gender in q_norm:
            q = f"{footwear} {q}".strip()
        elif gender:
            q = f"{footwear} {gender} {q}".strip()
        else:
            q = f"{footwear} {q}".strip()
        q_norm = remove_vietnamese_accents(q).lower()

    if has_height and not any(m in q_norm for m in _HEIGHT_QUERY_MARKERS):
        if "dang-dai" in path or "co-cao" in path:
            q = f"{q} cổ cao".strip()
        elif "chieu-cao" in path or "de-cao" in path or "cao-got" in path:
            q = f"{q} cao gót".strip()
        else:
            q = f"{q} đế cao".strip()

    return _dedupe_adjacent_words(re.sub(r"\s+", " ", q).strip())


def _dedupe_adjacent_words(text: str) -> str:
    out: list[str] = []
    for w in (text or "").split():
        if out and remove_vietnamese_accents(out[-1]).lower() == remove_vietnamese_accents(w).lower():
            continue
        out.append(w)
    return " ".join(out)


def strip_material_tokens_from_keywords(text: str) -> str:
    """Bỏ từ chỉ mang nghĩa chất liệu (vd vải, bông) — giữ loại SP + đặc tính."""
    if not (text or "").strip():
        return ""
    kept: list[str] = []
    for word in (text or "").split():
        norm = remove_vietnamese_accents(word).lower().strip()
        if norm in _MATERIAL_ONLY_WORDS:
            continue
        kept.append(word)
    return " ".join(kept).strip()


def strip_vendor_tokens_from_keywords(text: str, legacy_path: str = "") -> str:
    """Bỏ từ trong chuỗi tìm kiếm trùng mã NCC / segment lạ từ URL."""
    vendors = vendor_slug_tokens_from_path(legacy_path)
    if not text or not vendors:
        return (text or "").strip()
    kept: list[str] = []
    for word in (text or "").split():
        norm = remove_vietnamese_accents(word).lower().strip()
        if norm in vendors:
            continue
        kept.append(word)
    return " ".join(kept).strip()
