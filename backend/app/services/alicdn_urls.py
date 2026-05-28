"""
Chuẩn hoá URL ảnh sản phẩm trước khi lưu DB.

Quy tắc:
- …-cib.jpg_800x800q90.jpg  → …-cib.jpg
- …-cib.jpg_570x….jpg_.webp → …-cib.jpg
- …fx_pic_center.webp_570x….jpg → …fx_pic_center.webp
- …fx_pic_center.webp.jpg (lỗi migrate cũ) → …fx_pic_center.webp
- Không bao giờ thêm .jpg vào URL .webp/.png gốc.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List

_IMG_KEYS = ("img", "image", "image_url", "imageUrl", "url", "thumb", "picture")
_IMAGE_JSON_KEYS = ("images", "gallery", "colors", "product_info")
_EXTRA_LIST_KEYS = ("color_image_urls", "detail_block_images_1688")
_SUPPLIER_IMAGE_BLOCK_MARKERS = ("viposeller", "viettelidc.com.vn")
_FIRST_JPG = re.compile(r"\.jpg", flags=re.I)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+|//[^\s\"'<>]+", flags=re.I)
_WEBP_RESIZE_SUFFIX = re.compile(r"(_\d+x\d+q?\d*|\.sum)\.(jpg|jpeg|png|webp)$", flags=re.I)


def truncate_alicdn_url_to_first_jpg(url: str) -> str:
    """Cắt URL ảnh tại cụm .jpg đầu tiên (bỏ mọi hậu tố phía sau)."""
    u = (url or "").strip()
    if not u:
        return u
    m = _FIRST_JPG.search(u)
    if not m:
        return u
    return u[: m.end()]


def _split_url_query(url: str) -> tuple[str, str]:
    base, sep, query = url.partition("?")
    return base, query if sep else ""


def _join_url_query(base: str, query: str) -> str:
    return f"{base}?{query}" if query else base


def normalize_product_image_url(url: str) -> str:
    """Chuẩn hoá một URL ảnh trước khi lưu DB."""
    u = _scheme_normalize(url)
    if not u:
        return ""

    base, query = _split_url_query(u)

    # Sửa lỗi migrate cũ — không giữ .webp.jpg / .png.jpg
    base = re.sub(r"\.webp\.jpg$", ".webp", base, flags=re.I)
    base = re.sub(r"\.png\.jpg$", ".png", base, flags=re.I)

    lower = base.lower()

    # File .jpg gốc bị gắn thêm hậu tố nén: …cib.jpg_800x800q90.jpg
    if re.search(r"\.jpg[._?]", base, flags=re.I):
        base = truncate_alicdn_url_to_first_jpg(base)

    # File .webp / .png — chỉ bỏ hậu tố resize, không đổi đuôi gốc
    elif ".webp" in lower:
        base = _WEBP_RESIZE_SUFFIX.sub("", base)
        base = re.sub(r"\.webp\.jpg$", ".webp", base, flags=re.I)
    elif lower.endswith(".png") or ".png_" in lower:
        base = _WEBP_RESIZE_SUFFIX.sub("", base)
        base = re.sub(r"\.png\.jpg$", ".png", base, flags=re.I)

    out = _join_url_query(base, query)
    return "" if is_blocked_supplier_image_url(out) else out


def url_needs_image_normalization(url: str) -> bool:
    raw = _scheme_normalize(url)
    if not raw:
        return False
    lower = raw.lower()
    if ".webp.jpg" in lower or ".png.jpg" in lower:
        return True
    if re.search(r"\.jpg[._?]", raw, flags=re.I):
        return True
    if ".webp_" in lower and _WEBP_RESIZE_SUFFIX.search(raw):
        return True
    fixed = normalize_product_image_url(raw)
    return bool(fixed and fixed != raw)


def url_has_double_jpg_suffix(url: str) -> bool:
    return url_needs_image_normalization(url)


def _looks_like_image_url(value: str) -> bool:
    u = (value or "").strip()
    if not u:
        return False
    lower = u.lower()
    if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("//")):
        return False
    return (
        ".jpg" in lower
        or ".webp" in lower
        or ".png" in lower
        or "alicdn" in lower
        or "/img/ibank/" in lower
        or "imgextra" in lower
    )


def normalize_image_urls_in_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return text

    def _repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        if not _looks_like_image_url(raw):
            return raw
        fixed = normalize_product_image_url(raw)
        return fixed or raw

    return _URL_IN_TEXT.sub(_repl, text)


def normalize_image_urls_deep(value: Any) -> Any:
    if isinstance(value, str):
        if _looks_like_image_url(value):
            fixed = normalize_product_image_url(value)
            return fixed or value
        return value
    if isinstance(value, list):
        return [normalize_image_urls_deep(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize_image_urls_deep(item) for key, item in value.items()}
    return value


def _scheme_normalize(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("//"):
        u = f"https:{u}"
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    return u


def is_blocked_supplier_image_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return any(marker in u for marker in _SUPPLIER_IMAGE_BLOCK_MARKERS)


def normalize_excel_product_image_urls(product_data: Dict[str, Any]) -> None:
    """In-place: mọi cột/link ảnh trên payload sản phẩm."""
    normalize_product_data_image_urls_for_db(product_data)


def normalize_product_data_image_urls_for_db(product_data: Dict[str, Any]) -> None:
    """Chuẩn hoá mọi URL ảnh in-place trước khi ghi DB hoặc draft."""
    mi = product_data.get("main_image")
    if isinstance(mi, str) and mi.strip():
        product_data["main_image"] = normalize_product_image_url(mi)

    for key in _IMAGE_JSON_KEYS + _EXTRA_LIST_KEYS:
        val = product_data.get(key)
        if val is not None:
            product_data[key] = normalize_image_urls_deep(val)

    desc = product_data.get("description")
    if isinstance(desc, str) and desc.strip():
        product_data["description"] = normalize_image_urls_in_text(desc)


def normalize_product_image_record(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-copy + chuẩn hoá mọi trường ảnh trong payload sản phẩm."""
    out = copy.deepcopy(product_data)
    normalize_product_data_image_urls_for_db(out)
    return out


def iter_bad_image_urls_in_record(product_data: Dict[str, Any]) -> Iterable[str]:
    """Yield URL ảnh chưa chuẩn (audit / migrate)."""

    def walk(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            if _looks_like_image_url(value) and url_needs_image_normalization(value):
                yield value
            return
        if isinstance(value, list):
            for item in value:
                yield from walk(item)
            return
        if isinstance(value, dict):
            for item in value.values():
                yield from walk(item)

    yield from walk(product_data)
