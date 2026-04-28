"""
Upload file lên Bunny.net Storage Zone (HTTPS API).
Chú ý: Pull Zone CDN phải trỏ cùng storage zone để URL public có hiệu lực.

Env:
  BUNNY_STORAGE_ZONE_NAME   — VD: 188-com-vn-cdn
  BUNNY_STORAGE_ACCESS_KEY — password API (Dashboard → Storage → Credentials)
  BUNNY_CDN_PUBLIC_BASE     — hostname Pull Zone VD: https://188comvn.b-cdn.net (hoặc custom sau CNAME + SSL)
"""
from __future__ import annotations

import mimetypes
from typing import Optional

import requests


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
