# backend/app/utils/vietnamese.py - Chuẩn hóa tiếng Việt cho tìm kiếm
"""Chuẩn hóa tiếng Việt: bỏ dấu, mapping từ phổ biến."""

import unicodedata
import re
from typing import List, Optional

# Mapping bỏ dấu tiếng Việt (thủ công, chuẩn Unicode)
VIETNAMESE_ACCENT_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd',
    'À': 'a', 'Á': 'a', 'Ả': 'a', 'Ã': 'a', 'Ạ': 'a',
    'Ă': 'a', 'Ằ': 'a', 'Ắ': 'a', 'Ẳ': 'a', 'Ẵ': 'a', 'Ặ': 'a',
    'Â': 'a', 'Ầ': 'a', 'Ấ': 'a', 'Ẩ': 'a', 'Ẫ': 'a', 'Ậ': 'a',
    'È': 'e', 'É': 'e', 'Ẻ': 'e', 'Ẽ': 'e', 'Ẹ': 'e',
    'Ê': 'e', 'Ề': 'e', 'Ế': 'e', 'Ể': 'e', 'Ễ': 'e', 'Ệ': 'e',
    'Ì': 'i', 'Í': 'i', 'Ỉ': 'i', 'Ĩ': 'i', 'Ị': 'i',
    'Ò': 'o', 'Ó': 'o', 'Ỏ': 'o', 'Õ': 'o', 'Ọ': 'o',
    'Ô': 'o', 'Ồ': 'o', 'Ố': 'o', 'Ổ': 'o', 'Ỗ': 'o', 'Ộ': 'o',
    'Ơ': 'o', 'Ờ': 'o', 'Ớ': 'o', 'Ở': 'o', 'Ỡ': 'o', 'Ợ': 'o',
    'Ù': 'u', 'Ú': 'u', 'Ủ': 'u', 'Ũ': 'u', 'Ụ': 'u',
    'Ư': 'u', 'Ừ': 'u', 'Ứ': 'u', 'Ử': 'u', 'Ữ': 'u', 'Ự': 'u',
    'Ỳ': 'y', 'Ý': 'y', 'Ỷ': 'y', 'Ỹ': 'y', 'Ỵ': 'y',
    'Đ': 'd',
}


def remove_vietnamese_accents(text: str) -> str:
    """Chuyển tiếng Việt có dấu thành không dấu."""
    if not text or not isinstance(text, str):
        return ""
    result = []
    for c in text:
        result.append(VIETNAMESE_ACCENT_MAP.get(c, c))
    return "".join(result)


# Mapping từ phổ biến: thiếu dấu/sai chữ -> đúng (thời trang, giày dép)
COMMON_WORD_MAPPING = {
    "long": "lông", "lon": "lông", "longg": "lông",
    "de": "đế", "dee": "đế",
    "dep": "dép", "depp": "dép",
    "giay": "giày", "day": "giày",
    "ao": "áo",
    "quan": "quần",
    "tui": "túi",
    "vi": "ví", "vee": "ví",
    "nam": "nam",  # nam không đổi
    "nan": "nam",  # lỗi gõ phổ biến
    "nu": "nữ", "nux": "nữ",
    "cao": "cao",  # có thể cao lông hoặc chiều cao - giữ nguyên
    "chealsea": "chelsea",
    "boot": "boot", "but": "boot",
    "da": "da",  # da (da bóng) - giữ
}


def apply_word_mapping(words: List[str]) -> List[str]:
    """Áp dụng mapping từ phổ biến cho danh sách từ."""
    result = []
    for w in words:
        w_lower = w.lower()
        result.append(COMMON_WORD_MAPPING.get(w_lower, w))
    return result


def normalize_for_search_no_accent(text: str) -> str:
    """Chuẩn hóa cho tìm kiếm: trim, lowercase, bỏ dấu."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip().lower()
    if not s:
        return ""
    return remove_vietnamese_accents(s)
