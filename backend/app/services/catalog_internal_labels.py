"""
Nhãn nội bộ Meta Commerce (`internal_label`) — lọc nhóm sản phẩm trong Commerce Manager.

Meta khuyến nghị dùng internal_label thay custom_label_0–4 khi tạo product set (cập nhật nhanh, không review lại SP).
Định dạng TSV: một nhãn `['iphone_15']`, nhiều nhãn `['phu_kien_dien_thoai','iphone_15','iphone_16']`.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from app.models.product import Product

_MAX_LABELS_PER_PRODUCT = 32
_MAX_LABEL_LEN = 110

_PHONE_ACCESSORY_KEYWORDS = (
    "phụ kiện điện thoại",
    "phu kien dien thoai",
    "ốp lưng",
    "op lung",
    "miếng dán",
    "mieng dan",
    "cường lực",
    "cuong luc",
    "phone case",
    "screen protector",
    "ốp điện thoại",
    "op dien thoai",
)

_DEVICE_HINT_KEYWORDS = (
    "iphone",
    "ipad",
    "samsung",
    "galaxy",
    "xiaomi",
    "redmi",
    "oppo",
    "vivo",
    "realme",
    "huawei",
    "honor",
    "oneplus",
    "pixel",
)

_RE_IPHONE = re.compile(
    r"iphone\s*(\d{1,2})(?:\s*(pro\s*max|pro|plus|mini|max))?",
    re.I,
)
_RE_IPHONE_SLASH = re.compile(r"iphone\s*(\d{1,2})\s*/\s*(\d{1,2})", re.I)
_RE_SAMSUNG_S = re.compile(
    r"(?<!tab\s)(?<!watch\s)(?:samsung\s+)?(?:galaxy\s+)?s\s*(\d{1,2})\s*(ultra|plus|fe|edge)?\b",
    re.I,
)
_RE_SAMSUNG_ULTRA_SHORT = re.compile(r"\bultra\s*(\d{2})\b", re.I)
_RE_SAMSUNG_A = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?a\s*(\d{1,2})\s*(?:5g|lite|s)?\b",
    re.I,
)
_RE_SAMSUNG_A_SLASH = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?a\s*(\d{1,2})\s*/\s*a?\s*(\d{1,2})\b",
    re.I,
)
_RE_SAMSUNG_M = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?m\s*(\d{1,2})\s*(?:5g|lite)?\b",
    re.I,
)
_RE_SAMSUNG_F = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?f\s*(\d{1,2})\s*(?:5g)?\b",
    re.I,
)
_RE_SAMSUNG_J = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?j\s*(\d{1,2})\+?\b",
    re.I,
)
_RE_SAMSUNG_TAB = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?tab\s*(s|a)\s*(\d{1,2})(?:\s*(ultra|plus|fe|lite))?\b",
    re.I,
)
_RE_SAMSUNG_WATCH = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?watch\s*(\d{1,2})(?:\s*(ultra|classic|fe))?\b",
    re.I,
)
_RE_SAMSUNG_BUDS = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?buds\s*(\d{1,2})?(?:\s*(pro|fe|live))?\b",
    re.I,
)
_RE_NOTE = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?note\s*(\d{1,2})(?:\s*(ultra|plus))?",
    re.I,
)
_RE_Z_FLIP_FOLD = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?z\s*(flip|fold)\s*(\d{1,2})?",
    re.I,
)
_RE_BRAND_GALAXY = re.compile(r"\bgalaxy\b", re.I)

_RE_BRAND_SAMSUNG = re.compile(r"\bsamsung\b", re.I)
_RE_BRAND_IPHONE = re.compile(r"\biphone\b", re.I)
_RE_BRAND_XIAOMI = re.compile(r"\b(?:xiaomi|redmi)\b", re.I)
_RE_BRAND_OPPO = re.compile(r"\b(?:oppo|realme|vivo)\b", re.I)


def _normalize_label_token(raw: str) -> str:
    t = re.sub(r"[^\w]+", "_", (raw or "").strip().lower())
    t = re.sub(r"_+", "_", t).strip("_")
    return t[:_MAX_LABEL_LEN]


def _uniq_labels(labels: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in labels:
        lbl = _normalize_label_token(raw)
        if not lbl or lbl in seen:
            continue
        seen.add(lbl)
        out.append(lbl)
        if len(out) >= _MAX_LABELS_PER_PRODUCT:
            break
    return out


def _format_meta_internal_label_cell(labels: List[str]) -> str:
    if not labels:
        return ""
    quoted = ",".join(f"'{lbl}'" for lbl in labels)
    return f"[{quoted}]"


def _labels_from_product_info_override(product: Product) -> Optional[str]:
    raw = getattr(product, "product_info", None)
    if not isinstance(raw, dict):
        return None
    val = raw.get("internal_label")
    if val is None:
        val = raw.get("internal_labels")
    if val is None:
        return None
    if isinstance(val, list):
        labels = _uniq_labels(str(x) for x in val if x is not None and str(x).strip())
        return _format_meta_internal_label_cell(labels) if labels else ""
    s = str(val).strip()
    if not s:
        return ""
    if s.startswith("["):
        return s
    parts = [p.strip() for p in re.split(r"[,;|]", s) if p.strip()]
    labels = _uniq_labels(parts)
    return _format_meta_internal_label_cell(labels) if labels else ""


def _product_text_blob(product: Product) -> str:
    parts = [
        getattr(product, "name", None),
        getattr(product, "category", None),
        getattr(product, "subcategory", None),
        getattr(product, "sub_subcategory", None),
    ]
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())


def is_phone_accessory_product(product: Product) -> bool:
    hay = _product_text_blob(product).lower()
    if any(k in hay for k in _PHONE_ACCESSORY_KEYWORDS):
        return True
    if any(k in hay for k in _DEVICE_HINT_KEYWORDS) and any(
        k in hay for k in ("ốp", "op ", "case", "dán", "dan ", "bao", "cover", "cường", "cuong")
    ):
        return True
    return False


def _append_samsung_s_labels(found: List[str], num: str, variant: str) -> None:
    found.append("samsung_galaxy_s")
    found.append(f"samsung_s{num}")
    v = (variant or "").lower()
    if v == "ultra":
        found.append(f"samsung_s{num}_ultra")
        found.append(f"samsung_ultra_{num}")
    elif v == "edge":
        found.append(f"samsung_s{num}_edge")
    elif v:
        found.append(f"samsung_s{num}_{v}")


def extract_phone_device_labels(text: str) -> List[str]:
    """Trích nhãn thiết bị từ tiêu đề SP (iphone_16, samsung_s24_ultra, samsung_a54, …)."""
    t = (text or "").strip()
    if not t:
        return []

    found: List[str] = []

    for m in _RE_IPHONE_SLASH.finditer(t):
        found.append(f"iphone_{m.group(1)}")
        found.append(f"iphone_{m.group(2)}")

    for m in _RE_IPHONE.finditer(t):
        num = m.group(1)
        variant = (m.group(2) or "").replace(" ", "_").lower()
        if variant:
            found.append(f"iphone_{num}_{variant}")
        found.append(f"iphone_{num}")

    # Samsung — thứ tự: Tab/Watch/Buds trước S để tránh Tab S9 → samsung_s9.
    for m in _RE_SAMSUNG_TAB.finditer(t):
        series = (m.group(1) or "").lower()
        num = m.group(2)
        variant = (m.group(3) or "").lower()
        found.append("samsung_galaxy_tab")
        found.append(f"samsung_tab_{series}{num}")
        if variant:
            found.append(f"samsung_tab_{series}{num}_{variant}")

    for m in _RE_SAMSUNG_WATCH.finditer(t):
        num = m.group(1)
        variant = (m.group(2) or "").lower()
        found.append("samsung_galaxy_watch")
        found.append(f"samsung_watch_{num}")
        if variant:
            found.append(f"samsung_watch_{num}_{variant}")

    for m in _RE_SAMSUNG_BUDS.finditer(t):
        gen = m.group(1)
        variant = (m.group(2) or "").lower()
        found.append("samsung_galaxy_buds")
        if gen:
            found.append(f"samsung_buds_{gen}")
            if variant:
                found.append(f"samsung_buds_{gen}_{variant}")
        elif variant:
            found.append(f"samsung_buds_{variant}")

    for m in _RE_SAMSUNG_A_SLASH.finditer(t):
        found.append("samsung_galaxy_a")
        found.append(f"samsung_a{m.group(1)}")
        found.append(f"samsung_a{m.group(2)}")

    for m in _RE_SAMSUNG_A.finditer(t):
        found.append("samsung_galaxy_a")
        found.append(f"samsung_a{m.group(1)}")

    for m in _RE_SAMSUNG_M.finditer(t):
        found.append("samsung_galaxy_m")
        found.append(f"samsung_m{m.group(1)}")

    for m in _RE_SAMSUNG_F.finditer(t):
        found.append("samsung_galaxy_f")
        found.append(f"samsung_f{m.group(1)}")

    for m in _RE_SAMSUNG_J.finditer(t):
        found.append("samsung_galaxy_j")
        found.append(f"samsung_j{m.group(1)}")

    for m in _RE_NOTE.finditer(t):
        num = m.group(1)
        variant = (m.group(2) or "").lower()
        found.append("samsung_galaxy_note")
        found.append(f"samsung_note_{num}")
        if variant:
            found.append(f"samsung_note_{num}_{variant}")

    for m in _RE_Z_FLIP_FOLD.finditer(t):
        kind = (m.group(1) or "").lower()
        gen = m.group(2)
        found.append("samsung_galaxy_z")
        found.append(f"samsung_z_{kind}")
        if gen:
            found.append(f"samsung_z_{kind}_{gen}")

    for m in _RE_SAMSUNG_S.finditer(t):
        _append_samsung_s_labels(found, m.group(1), m.group(2) or "")

    for m in _RE_SAMSUNG_ULTRA_SHORT.finditer(t):
        found.append(f"samsung_ultra_{m.group(1)}")

    # Nhãn hãng / dòng — Meta khớp nguyên nhãn; `samsung` ≠ `samsung_s26_plus`.
    if _RE_BRAND_SAMSUNG.search(t) or _RE_BRAND_GALAXY.search(t):
        found.append("samsung")
    if _RE_BRAND_GALAXY.search(t):
        found.append("samsung_galaxy")
    if _RE_BRAND_IPHONE.search(t):
        found.append("iphone")
    if _RE_BRAND_XIAOMI.search(t):
        found.append("xiaomi")
    if _RE_BRAND_OPPO.search(t):
        found.append("oppo")

    return _uniq_labels(found)


def meta_internal_labels_for_product(product: Product) -> str:
    """
    Ô `internal_label` cho feed Meta catalogue.
    Ưu tiên `product_info.internal_label` / `internal_labels` nếu admin đã gán tay.
    """
    override = _labels_from_product_info_override(product)
    if override is not None:
        return override

    labels: List[str] = []
    if is_phone_accessory_product(product):
        labels.append("phu_kien_dien_thoai")
        name = getattr(product, "name", "") or ""
        labels.extend(extract_phone_device_labels(name))

    return _format_meta_internal_label_cell(_uniq_labels(labels))
