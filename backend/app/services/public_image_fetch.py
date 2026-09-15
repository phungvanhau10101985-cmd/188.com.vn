"""Tải ảnh public http(s) cho tính năng dán link tìm theo ảnh (tránh CORS trình duyệt)."""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests

from app.services.nanoai_partner_search import MAX_IMAGE_BYTES

FETCH_TIMEOUT_SEC = 15
MAX_REDIRECTS = 5
FETCH_UA = "Mozilla/5.0 (compatible; 188-image-fetch/1.0; +https://188.com.vn)"


class PublicImageFetchError(ValueError):
    """Link không hợp lệ hoặc không phải ảnh."""


def _host_is_blocked(hostname: str, port: Optional[int]) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    if host.endswith(".internal") or host.endswith(".lan"):
        return True
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return True
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def assert_public_http_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise PublicImageFetchError("Dán link ảnh (https://…) vào ô link.")
    if len(raw) > 2000:
        raise PublicImageFetchError("Link quá dài.")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise PublicImageFetchError("Link cần bắt đầu bằng http:// hoặc https://")
    host = parsed.hostname
    port = parsed.port
    if _host_is_blocked(host or "", port):
        raise PublicImageFetchError("Không hỗ trợ link máy nội bộ.")
    return raw


def sniff_image_mime(raw: bytes, content_type: str = "") -> Optional[str]:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct.startswith("image/") and ct not in {"image/svg+xml", "image/svg"}:
        return ct
    return None


def _read_limited(resp: requests.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_IMAGE_BYTES:
            raise PublicImageFetchError("Ảnh vượt quá ~5 MB")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_public_image_bytes(url: str) -> Tuple[bytes, str]:
    current = assert_public_http_url(url)
    headers = {"User-Agent": FETCH_UA, "Accept": "image/*,*/*;q=0.8"}
    for _ in range(MAX_REDIRECTS + 1):
        try:
            resp = requests.get(
                current,
                timeout=FETCH_TIMEOUT_SEC,
                stream=True,
                allow_redirects=False,
                headers=headers,
            )
        except requests.RequestException as exc:
            raise PublicImageFetchError("Không tải được ảnh từ link.") from exc

        if resp.is_redirect or resp.status_code in {301, 302, 303, 307, 308}:
            loc = (resp.headers.get("Location") or "").strip()
            if not loc:
                raise PublicImageFetchError("Link ảnh chuyển hướng không hợp lệ.")
            current = assert_public_http_url(urljoin(current, loc))
            continue

        if resp.status_code != 200:
            raise PublicImageFetchError(f"Máy chủ ảnh trả lỗi ({resp.status_code}).")

        raw = _read_limited(resp)
        if not raw:
            raise PublicImageFetchError("Link không trỏ tới file ảnh (JPEG, PNG, …).")
        mime = sniff_image_mime(raw, resp.headers.get("content-type") or "")
        if not mime:
            raise PublicImageFetchError("Link không trỏ tới file ảnh (JPEG, PNG, …).")
        return raw, mime

    raise PublicImageFetchError("Link ảnh chuyển hướng quá nhiều lần.")
