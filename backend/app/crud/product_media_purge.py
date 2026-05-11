"""Gỡ URL ảnh khỏi bản ghi Product khi xác nhận URL không tồn tại (404/410).
Dùng cùng logic khớp URL lỏng (scheme/host/path) với storefront."""
from __future__ import annotations

import logging
from typing import Any, List, Tuple
from urllib.parse import urlparse, unquote

import requests
from sqlalchemy.orm import Session

from app.models.product import Product

logger = logging.getLogger(__name__)


def _host_key(netloc: str) -> str:
    h = (netloc or "").strip().lower()
    if h.startswith("www."):
        h = h[4:]
    return h


def _path_key(path: str) -> str:
    try:
        p = unquote((path or "").strip())
    except Exception:
        p = (path or "").strip()
    return p.rstrip("/") or "/"


def image_urls_equivalent(stored: str, target: str) -> bool:
    """Khớp URL ảnh giữa DB (đủ kiểu) và URL client/backend kiểm tra."""
    sa = (stored or "").strip()
    ta = (target or "").strip()
    if not sa or not ta:
        return False
    if sa == ta:
        return True
    try:
        pa = urlparse(sa if "://" in sa else ("https://" + sa.lstrip("/")))
        pb = urlparse(ta if "://" in ta else ("https://" + ta.lstrip("/")))
        if sa.startswith("/") and not ta.startswith("/") and pb.path:
            if _path_key(sa) == _path_key(pb.path) and pb.netloc:
                return True
        if ta.startswith("/") and not sa.startswith("/") and pa.path:
            if _path_key(ta) == _path_key(pa.path) and pa.netloc:
                return True
        if pa.netloc and pb.netloc:
            return _host_key(pa.netloc) == _host_key(pb.netloc) and _path_key(
                pa.path
            ) == _path_key(pb.path)
    except Exception:
        pass
    return False


def _nested_json_contains_image_url(obj: Any, url: str) -> bool:
    if isinstance(obj, str):
        return bool(obj.strip()) and (
            obj.strip().startswith(("http://", "https://", "//", "/"))
            and image_urls_equivalent(obj, url)
        )
    if isinstance(obj, list):
        return any(_nested_json_contains_image_url(x, url) for x in obj)
    if isinstance(obj, dict):
        return any(_nested_json_contains_image_url(v, url) for v in obj.values())
    return False


def product_references_media_url(product: Product, url: str) -> bool:
    mi = getattr(product, "main_image", None) or ""
    if isinstance(mi, str) and mi.strip() and image_urls_equivalent(mi, url):
        return True
    for lst in (
        getattr(product, "images", None) or [],
        getattr(product, "gallery", None) or [],
    ):
        if not isinstance(lst, list):
            continue
        for item in lst:
            if isinstance(item, str) and item.strip() and image_urls_equivalent(item, url):
                return True
    colors = getattr(product, "colors", None) or []
    if isinstance(colors, list):
        for c in colors:
            if isinstance(c, dict):
                img = c.get("img")
                if isinstance(img, str) and img.strip() and image_urls_equivalent(img, url):
                    return True
    pi = getattr(product, "product_info", None)
    if _nested_json_contains_image_url(pi, url):
        return True
    return False


def _deep_scrub_url(obj: Any, url: str) -> Tuple[Any, bool]:
    if isinstance(obj, str):
        if image_urls_equivalent(obj, url):
            return "", True
        return obj, False
    if isinstance(obj, list):
        out: List[Any] = []
        changed = False
        for x in obj:
            nx, c = _deep_scrub_url(x, url)
            if isinstance(nx, str) and not nx.strip() and c:
                continue
            out.append(nx)
            changed = changed or c
        return out, changed
    if isinstance(obj, dict):
        out_d: dict = {}
        changed = False
        for k, v in obj.items():
            nv, c = _deep_scrub_url(v, url)
            out_d[k] = nv
            changed = changed or c
        return out_d, changed
    return obj, False


def _filter_list(lst: Any, url: str) -> Tuple[List[str], bool]:
    if not lst or not isinstance(lst, list):
        return ([] if lst is None else [], False)
    out: List[str] = []
    changed = False
    for item in lst:
        if isinstance(item, str):
            if image_urls_equivalent(item, url):
                changed = True
                continue
            out.append(item)
    return out, changed


def is_remote_media_url_dead(url: str, timeout_sec: float = 6.0) -> bool:
    """True khi server trả 404 hoặc 410 (HEAD rồi GET tối thiểu nếu cần)."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False
    try:
        h = requests.head(u, timeout=timeout_sec, allow_redirects=True)
        sc = int(h.status_code)
        if sc in (404, 410):
            return True
        if sc in (405, 501) or sc >= 500 or sc in (401, 403):
            g = requests.get(
                u,
                timeout=timeout_sec,
                allow_redirects=True,
                headers={"Range": "bytes=0-0"},
            )
            try:
                return int(g.status_code) in (404, 410)
            finally:
                g.close()
        return False
    except requests.RequestException as e:
        logger.debug("dead media probe failed %s: %s", u[:120], e)
        return False


def purge_dead_media_url_from_product(product: Product, url: str) -> Tuple[bool, List[str]]:
    """
    Gỡ mọi tham chiếu tới `url` (khớp lỏng) trên `product`.
    Trả về (đã đổi, danh sách trường đã đụng).
    """
    touched: List[str] = []

    imgs, ch_i = _filter_list(getattr(product, "images", None) or [], url)
    if ch_i:
        product.images = imgs
        touched.append("images")

    gall, ch_g = _filter_list(getattr(product, "gallery", None) or [], url)
    if ch_g:
        product.gallery = gall
        touched.append("gallery")

    colors = getattr(product, "colors", None) or []
    if isinstance(colors, list):
        new_colors = []
        ch_c = False
        for c in colors:
            if isinstance(c, dict):
                nc = dict(c)
                img = nc.get("img")
                if isinstance(img, str) and image_urls_equivalent(img, url):
                    nc.pop("img", None)
                    ch_c = True
                new_colors.append(nc)
            else:
                new_colors.append(c)
        if ch_c:
            product.colors = new_colors
            touched.append("colors")

    mi = getattr(product, "main_image", None) or ""
    if isinstance(mi, str) and mi.strip() and image_urls_equivalent(mi, url):
        product.main_image = None
        touched.append("main_image")

    pi = getattr(product, "product_info", None)
    if pi is not None:
        new_pi, ch_pi = _deep_scrub_url(pi, url)
        if ch_pi:
            product.product_info = new_pi
            touched.append("product_info")

    if "main_image" in touched or "images" in touched:
        mi2 = getattr(product, "main_image", None)
        imgs2 = getattr(product, "images", None) or []
        if (not mi2 or not str(mi2).strip()) and isinstance(imgs2, list):
            next_main = None
            for item in imgs2:
                if isinstance(item, str) and item.strip():
                    next_main = item.strip()
                    break
            product.main_image = next_main

    return (len(touched) > 0, touched)


def run_purge_dead_media_if_eligible(db: Session, product: Product, url: str) -> dict:
    """
    Kiểm tra URL không tồn tại và gắn với sản phẩm → gỡ khỏi DB.
    Trả payload JSON-safe cho API.
    """
    if not product_references_media_url(product, url):
        return {"ok": False, "reason": "url_not_on_product"}

    if not is_remote_media_url_dead(url):
        return {"ok": False, "reason": "url_still_reachable_or_probe_failed"}

    changed, touched = purge_dead_media_url_from_product(product, url)
    if changed:
        from app.crud import product as product_crud

        db.commit()
        db.refresh(product)
        try:
            product_crud._maybe_schedule_category_gemini_for_product(db, product)
        except Exception:
            pass
        try:
            from app.utils.ttl_cache import cache as ttl_cache

            ttl_cache.invalidate_all()
        except Exception:
            pass
        return {"ok": True, "removed": True, "fields": touched}
    return {"ok": True, "removed": False, "fields": []}
