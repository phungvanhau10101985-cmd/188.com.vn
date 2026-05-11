"""
Upload / xoá file Bunny.net Storage Zone (HTTPS API).
Chú ý: Pull Zone CDN phải trỏ cùng storage zone để URL public có hiệu lực.

Env:
  BUNNY_STORAGE_ZONE_NAME   — VD: 188-com-vn-cdn
  BUNNY_STORAGE_ACCESS_KEY — password API (Dashboard → Storage → Credentials)
  BUNNY_CDN_PUBLIC_BASE     — hostname Pull Zone VD: https://188comvn.b-cdn.net (hoặc custom sau CNAME + SSL)
  MERCHANT_FEED_IMAGE_BASE_URL — khi khác BUNNY_CDN_PUBLIC_BASE nhưng vẫn cùng Bunny (thêm host để nhận URL xoá)
  BUNNY_DELETE_ON_PRODUCT_DELETE — true (mặc định): xoá object khi xoá sản phẩm DB; false = không gọi DELETE
"""
from __future__ import annotations

import logging
import mimetypes
from typing import Any, Iterable, List, Optional, Set
from urllib.parse import urlparse

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

BUNNY_API_BASE = "https://storage.bunnycdn.com"


def build_public_object_url(public_base: str, remote_relative_path: str) -> str:
    base = (public_base or "").strip().rstrip("/")
    rel = (remote_relative_path or "").strip().lstrip("/")
    if not base or not rel:
        return ""
    return f"{base}/{rel}"


def upload_file_to_zone(
    *,
    zone_name: str,
    access_key: str,
    remote_path: str,
    data: bytes,
    content_type: Optional[str] = None,
    timeout_sec: float = 120.0,
) -> None:
    """PUT object onto Bunny Storage. remote_path không dấu / đầu khi nhét vào URL (tự normalize)."""
    zp = zone_name.strip().strip("/")
    rp = remote_path.strip().lstrip("/")
    if not zp or not rp:
        raise ValueError("zone_name và remote_path không được rỗng")
    url = f"{BUNNY_API_BASE}/{zp}/{rp}"
    headers = {"AccessKey": access_key.strip()}
    ct = content_type or mimetypes.guess_type(remote_path)[0] or "application/octet-stream"
    headers["Content-Type"] = ct
    resp = requests.put(url, data=data, headers=headers, timeout=timeout_sec)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Bunny PUT {resp.status_code}: {resp.text[:400]}")


def delete_file_from_zone(
    *,
    zone_name: str,
    access_key: str,
    remote_path: str,
    timeout_sec: float = 60.0,
) -> bool:
    """
    DELETE object trên Bunny Storage. 200 = ok; 404 = đã không tồn tại (coi là thành công).
    """
    zp = zone_name.strip().strip("/")
    rp = remote_path.strip().lstrip("/")
    if not zp or not rp:
        return False
    if ".." in rp or rp.startswith("/"):
        return False
    url = f"{BUNNY_API_BASE}/{zp}/{rp}"
    headers = {"AccessKey": access_key.strip()}
    resp = requests.delete(url, headers=headers, timeout=timeout_sec)
    if resp.status_code in (200, 204):
        return True
    if resp.status_code == 404:
        return True
    logger.warning("Bunny DELETE %s → %s %s", rp, resp.status_code, (resp.text or "")[:300])
    return False


def _host_from_public_base(base: str) -> str:
    raw = (base or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    netloc = urlparse(raw).netloc.lower()
    if ":" in netloc:
        netloc = netloc.split(":")[0]
    return netloc


def _bunny_image_hosts_for_delete() -> Set[str]:
    """Host Pull Zone được coi là ảnh Bunny của site (để map URL → path storage)."""
    hosts: Set[str] = set()
    for base in (
        getattr(settings, "BUNNY_CDN_PUBLIC_BASE", ""),
        getattr(settings, "MERCHANT_FEED_IMAGE_BASE_URL", ""),
    ):
        h = _host_from_public_base(str(base))
        if h:
            hosts.add(h)
    return hosts


def collect_product_image_urls_for_bunny(product: Any) -> List[str]:
    """Gom mọi chuỗi URL có thể là ảnh từ model Product."""
    urls: List[str] = []

    def add(raw: Optional[str]) -> None:
        s = raw if isinstance(raw, str) else None
        if s and s.strip().lower().startswith(("http://", "https://")):
            urls.append(s.strip())

    add(getattr(product, "main_image", None))

    for key in ("images", "gallery"):
        seq = getattr(product, key, None) or []
        if isinstance(seq, list):
            for x in seq:
                add(x if isinstance(x, str) else None)

    colors = getattr(product, "colors", None) or []
    if isinstance(colors, list):
        for row in colors:
            if isinstance(row, dict):
                for fld in ("img", "image", "url", "src", "thumbnail"):
                    val = row.get(fld)
                    add(val if isinstance(val, str) else None)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                lk = str(k).lower()
                if lk in ("img", "image", "url", "src", "thumbnail", "main_image") and isinstance(v, str):
                    add(v)
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)

    pinfo = getattr(product, "product_info", None)
    if pinfo:
        walk(pinfo)

    return urls


def _url_to_storage_path(url: str, allowed_hosts: Set[str]) -> Optional[str]:
    try:
        u = urlparse(url.strip())
        if u.scheme not in ("http", "https"):
            return None
        host = u.netloc.lower()
        if ":" in host:
            host = host.split(":")[0]
        if host not in allowed_hosts:
            return None
        path = u.path.strip("/")
        if not path:
            return None
        segments = path.split("/")
        if ".." in segments:
            return None
        return path
    except Exception:
        return None


def delete_bunny_storage_objects_for_urls(urls: Iterable[str]) -> int:
    """
    Xóa các object trên Bunny ứng với URL thuộc host(s) CDN đã cấu hình. Trả số DELETE coi là thành công (kể cả 404).
    """
    zone = getattr(settings, "BUNNY_STORAGE_ZONE_NAME", "") or ""
    key = getattr(settings, "BUNNY_STORAGE_ACCESS_KEY", "") or ""
    if not zone or not key:
        logger.warning("Bunny xoá khi xoá SP: thiếu BUNNY_STORAGE_ZONE_NAME hoặc BUNNY_STORAGE_ACCESS_KEY — bỏ qua.")
        return 0

    hosts = _bunny_image_hosts_for_delete()
    if not hosts:
        return 0

    uniq: List[str] = []
    seen: Set[str] = set()
    for u in urls:
        rp = _url_to_storage_path(str(u), hosts)
        if rp and rp not in seen:
            seen.add(rp)
            uniq.append(rp)

    ok = 0
    for rp in uniq:
        if delete_file_from_zone(zone_name=zone, access_key=key, remote_path=rp):
            ok += 1
    return ok


def delete_bunny_assets_for_product(product: Any) -> int:
    """
    Best-effort: xoá file storage trên Bunny trùng URL ảnh của sản phẩm. Không ném exception ra ngoài.
    Đặt BUNNY_DELETE_ON_PRODUCT_DELETE=false để không gọi API DELETE.
    """
    if not settings.BUNNY_DELETE_ON_PRODUCT_DELETE:
        return 0
    try:
        urls = collect_product_image_urls_for_bunny(product)
        if not urls:
            return 0
        n = delete_bunny_storage_objects_for_urls(urls)
        if n:
            logger.info("Đã xoá %s object Bunny cho sản phẩm product_id=%s", n, getattr(product, "product_id", "?"))
        return n
    except Exception as exc:
        logger.warning("Bunny xoá khi xoá SP — lỗi (vẫn giữ luồng xoá DB): %s", exc)
        return 0
