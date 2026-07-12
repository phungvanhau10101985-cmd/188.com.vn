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
    r"(?:samsung\s+)?(?:galaxy\s+)?s\s*(\d{1,2})\s*(ultra|plus|fe)?\b",
    re.I,
)
_RE_SAMSUNG_ULTRA_SHORT = re.compile(r"\bultra\s*(\d{2})\b", re.I)
_RE_NOTE = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?note\s*(\d{1,2})\b",
    re.I,
)
_RE_Z_FLIP_FOLD = re.compile(
    r"(?:samsung\s+)?(?:galaxy\s+)?z\s*(flip|fold)\s*(\d{1,2})?",
    re.I,
)


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


def extract_phone_device_labels(text: str) -> List[str]:
    """Trích nhãn thiết bị từ tiêu đề SP (iphone_16, samsung_s24_ultra, …)."""
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

    for m in _RE_SAMSUNG_S.finditer(t):
        num = m.group(1)
        variant = (m.group(2) or "").lower()
        if variant == "ultra":
            found.append(f"samsung_s{num}_ultra")
            found.append(f"samsung_ultra_{num}")
        elif variant:
            found.append(f"samsung_s{num}_{variant}")
        else:
            found.append(f"samsung_s{num}")

    for m in _RE_SAMSUNG_ULTRA_SHORT.finditer(t):
        found.append(f"samsung_ultra_{m.group(1)}")

    for m in _RE_NOTE.finditer(t):
        found.append(f"samsung_note_{m.group(1)}")

    for m in _RE_Z_FLIP_FOLD.finditer(t):
        kind = (m.group(1) or "").lower()
        gen = m.group(2)
        if gen:
            found.append(f"samsung_z_{kind}_{gen}")
        else:
            found.append(f"samsung_z_{kind}")

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
