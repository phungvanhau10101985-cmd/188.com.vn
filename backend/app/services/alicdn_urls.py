"""
Chuẩn hoá URL ảnh Alibaba CDN: bỏ hậu tố nén sau .jpg đầu tiên
(vd. ...-cib.jpg_220x220Q80.jpg_.webp → ...-cib.jpg).
"""
from __future__ import annotations

import re
from typing import Any, Dict

_IMG_KEYS = ("img", "image", "image_url", "imageUrl", "url", "thumb", "picture")
_SUPPLIER_IMAGE_BLOCK_MARKERS = ("viposeller", "viettelidc.com.vn")


def truncate_alicdn_url_to_first_jpg(url: str) -> str:
    u = (url or "").strip()
    if not u or "alicdn" not in u.lower():
        return u
    m = re.search(r"\.jpg", u, flags=re.I)
    if not m:
        return u
    return u[: m.end()]


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
    """In-place: main_image, images[], gallery[], colors[].* ảnh alicdn → tới .jpg đầu tiên."""

    def norm_one(s: str) -> str:
        u = truncate_alicdn_url_to_first_jpg(_scheme_normalize(s))
        return "" if is_blocked_supplier_image_url(u) else u

    mi = product_data.get("main_image")
    if isinstance(mi, str) and mi.strip():
        product_data["main_image"] = norm_one(mi)

    for key in ("images", "gallery"):
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
    if not isinstance(colors, list):
        return
    for item in colors:
        if not isinstance(item, dict):
            continue
        for ik in _IMG_KEYS:
            v = item.get(ik)
            if isinstance(v, str) and v.strip():
                item[ik] = norm_one(v)
