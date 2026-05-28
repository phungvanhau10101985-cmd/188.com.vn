"""
Chuẩn hoá URL ảnh sản phẩm: bỏ hậu tố nén sau cụm .jpg đầu tiên
(vd. ...-cib.jpg_800x800q90.jpg → ...-cib.jpg).
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List

_IMG_KEYS = ("img", "image", "image_url", "imageUrl", "url", "thumb", "picture")
_EXTRA_LIST_KEYS = ("color_image_urls", "detail_block_images_1688")
_SUPPLIER_IMAGE_BLOCK_MARKERS = ("viposeller", "viettelidc.com.vn")
_TRAILING_RESIZE_SUFFIX = re.compile(
    r"(_\d+x\d+q?\d*|\.sum)\.(jpg|jpeg|png|webp)$",
    flags=re.I,
)
_FIRST_JPG = re.compile(r"\.jpg", flags=re.I)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>]+|//[^\s\"'<>]+", flags=re.I)


def truncate_alicdn_url_to_first_jpg(url: str) -> str:
    """Cắt URL ảnh tại cụm .jpg đầu tiên (bỏ mọi hậu tố phía sau)."""
    u = (url or "").strip()
    if not u:
        return u
    m = _FIRST_JPG.search(u)
    if not m:
        return u
    return u[: m.end()]


def normalize_product_image_url(url: str) -> str:
    """Chuẩn hoá một URL ảnh trước khi lưu DB."""
    u = _scheme_normalize(url)
    if not u:
        return ""
    # …-cib.jpg_800x800q90.jpg hoặc …-cib.jpg_570x….jpg_.webp → cắt tại .jpg đầu tiên
    if re.search(r"\.jpg[._?]", u, flags=re.I):
        u = truncate_alicdn_url_to_first_jpg(u)
    # …center.webp_570x10000Q80.jpg → bỏ hậu tố, giữ .webp/.png gốc
    elif re.search(r"\.(?:webp|png|jpeg)[._]", u, flags=re.I):
        u = re.sub(r"(_\d+x\d+q?\d*|\.sum)\.(jpg|jpeg|png|webp)$", "", u, flags=re.I)
    else:
        u = _TRAILING_RESIZE_SUFFIX.sub(r".\2", u)
    # Sửa lỗi migrate cũ: …center.webp.jpg → …center.webp
    u = re.sub(r"\.webp\.jpg$", ".webp", u, flags=re.I)
    u = re.sub(r"\.png\.jpg$", ".png", u, flags=re.I)
    return "" if is_blocked_supplier_image_url(u) else u


def url_has_double_jpg_suffix(url: str) -> bool:
    raw = _scheme_normalize(url)
    if not raw:
        return False
    fixed = normalize_product_image_url(raw)
    return bool(fixed and fixed != raw)


def _looks_like_image_url(value: str) -> bool:
    u = (value or "").strip()
    if not u:
        return False
    lower = u.lower()
    if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("//")):
        return False
    return ".jpg" in lower or "alicdn" in lower or "/img/ibank/" in lower or "imgextra" in lower


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
    """In-place: main_image, images[], gallery[], colors[].*, product_info, description."""

    def norm_one(s: str) -> str:
        return normalize_product_image_url(s)

    mi = product_data.get("main_image")
    if isinstance(mi, str) and mi.strip():
        product_data["main_image"] = norm_one(mi)

    for key in ("images", "gallery", *_EXTRA_LIST_KEYS):
        lst = product_data.get(key)
        if not isinstance(lst, list):
            continue
        out = []
        for x in lst:
            if isinstance(x, str) and str(x).strip():
                u = norm_one(str(x))
                if u:
                    out.append(u)
            elif x:
                out.append(x)
        product_data[key] = out

    if not product_data.get("main_image"):
        imgs = product_data.get("images")
        if isinstance(imgs, list):
            first = next((x for x in imgs if isinstance(x, str) and x.strip()), "")
            if first:
                product_data["main_image"] = first

    colors = product_data.get("colors")
    if isinstance(colors, list):
        for item in colors:
            if not isinstance(item, dict):
                continue
            for ik in _IMG_KEYS:
                v = item.get(ik)
                if isinstance(v, str) and v.strip():
                    item[ik] = norm_one(v)

    pi = product_data.get("product_info")
    if pi is not None:
        product_data["product_info"] = normalize_image_urls_deep(pi)

    desc = product_data.get("description")
    if isinstance(desc, str) and desc.strip():
        product_data["description"] = normalize_image_urls_in_text(desc)


def normalize_product_data_image_urls_for_db(product_data: Dict[str, Any]) -> None:
    """Chuẩn hoá mọi URL ảnh in-place trước khi ghi DB hoặc draft."""
    normalize_excel_product_image_urls(product_data)


def normalize_product_image_record(product_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-copy + chuẩn hoá mọi trường ảnh trong payload sản phẩm."""
    out = copy.deepcopy(product_data)
    normalize_excel_product_image_urls(out)
    return out


def iter_bad_image_urls_in_record(product_data: Dict[str, Any]) -> Iterable[str]:
    """Yield URL ảnh còn hậu tố sau .jpg đầu tiên (audit)."""

    def walk(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            if _looks_like_image_url(value) and url_has_double_jpg_suffix(value):
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
