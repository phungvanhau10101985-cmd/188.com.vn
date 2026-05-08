"""
Chuẩn hoá URL ảnh Alibaba CDN: bỏ hậu tố nén sau .jpg đầu tiên
(vd. ...-cib.jpg_220x220Q80.jpg_.webp → ...-cib.jpg).
"""
from __future__ import annotations

import re
from typing import Any, Dict

_IMG_KEYS = ("img", "image", "image_url", "imageUrl", "url", "thumb", "picture")


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


def normalize_excel_product_image_urls(product_data: Dict[str, Any]) -> None:
    """In-place: main_image, images[], gallery[], colors[].* ảnh alicdn → tới .jpg đầu tiên."""

    def norm_one(s: str) -> str:
        return truncate_alicdn_url_to_first_jpg(_scheme_normalize(s))

    mi = product_data.get("main_image")
    if isinstance(mi, str) and mi.strip():
        product_data["main_image"] = norm_one(mi)

    for key in ("images", "gallery"):
        lst = product_data.get(key)
        if not isinstance(lst, list):
            continue
        product_data[key] = [
            norm_one(str(x)) if isinstance(x, str) and str(x).strip() else x for x in lst
        ]

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
