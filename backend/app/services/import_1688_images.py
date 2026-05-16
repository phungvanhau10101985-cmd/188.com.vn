from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

import requests

from app.core.config import settings
from app.services.bunny_storage import build_public_object_url, upload_file_to_zone
from app.services.image_raster_jpeg import raster_bytes_to_jpeg_bytes


def _can_upload_to_bunny() -> bool:
    return bool(settings.BUNNY_STORAGE_ZONE_NAME and settings.BUNNY_STORAGE_ACCESS_KEY and settings.BUNNY_CDN_PUBLIC_BASE)


def ingest_1688_images(product_data: Dict[str, Any], offer_id: str | None) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    if not settings.IMPORT_1688_DOWNLOAD_IMAGES:
        warnings.append("IMPORT_1688_DOWNLOAD_IMAGES=false; giữ URL ảnh gốc trong draft.")
        return product_data, warnings
    if not _can_upload_to_bunny():
        warnings.append("Bunny storage chưa cấu hình đủ; giữ URL ảnh gốc trong draft.")
        return product_data, warnings

    images = [x for x in product_data.get("images") or [] if isinstance(x, str) and x.strip()]
    if product_data.get("main_image") and product_data["main_image"] not in images:
        images.insert(0, product_data["main_image"])
    images = images[: settings.IMPORT_1688_MAX_IMAGES]

    uploaded: List[str] = []
    for idx, image_url in enumerate(images):
        try:
            resp = requests.get(
                image_url,
                timeout=25,
                headers={"User-Agent": settings.IMPORT_1688_USER_AGENT, "Referer": "https://detail.1688.com/"},
            )
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "image" not in content_type.lower() and len(resp.content) < 1024:
                raise RuntimeError(f"Nội dung tải về không giống ảnh ({content_type})")
            jpeg_bytes = raster_bytes_to_jpeg_bytes(resp.content)
            if not jpeg_bytes:
                raise RuntimeError("Không giải mã / chuyển ảnh sang JPEG được")
            ext = "jpg"
            digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:12]
            oid = offer_id or str(abs(hash(product_data.get("link_default") or "")))
            prefix = settings.BUNNY_UPLOAD_PATH_PREFIX.strip("/")
            web_prefix = settings.BUNNY_WEB_PUBLIC_PREFIX.strip("/")
            rel_prefix = "/".join(x for x in (prefix, web_prefix, "imports/1688", oid) if x)
            remote_path = f"{rel_prefix}/{idx + 1:02d}-{digest}.{ext}"
            upload_file_to_zone(
                zone_name=settings.BUNNY_STORAGE_ZONE_NAME,
                access_key=settings.BUNNY_STORAGE_ACCESS_KEY,
                remote_path=remote_path,
                data=jpeg_bytes,
                content_type="image/jpeg",
            )
            uploaded.append(build_public_object_url(settings.BUNNY_CDN_PUBLIC_BASE, remote_path))
        except Exception as exc:
            warnings.append(f"Không tải được ảnh {idx + 1}: {str(exc)[:160]}")

    if uploaded:
        next_data = dict(product_data)
        next_data["images"] = uploaded
        next_data["main_image"] = uploaded[0]
        info = dict(next_data.get("product_info") or {})
        info["source_images"] = images
        next_data["product_info"] = info
        return next_data, warnings
    warnings.append("Không tải được ảnh nào về Bunny; giữ URL gốc.")
    return product_data, warnings
