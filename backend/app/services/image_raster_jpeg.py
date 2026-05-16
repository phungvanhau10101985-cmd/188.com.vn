"""Decode raster (JPEG/PNG/WebP/...) → JPEG bytes; dùng chung import Bunny & admin upload."""

from __future__ import annotations

from typing import Optional

from app.core.config import settings


def raster_bytes_to_jpeg_bytes(image_bytes: bytes, *, quality: Optional[int] = None) -> Optional[bytes]:
    if not image_bytes:
        return None
    import cv2
    import numpy as np

    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    q = int(quality if quality is not None else (getattr(settings, "IMAGE_LOCALIZATION_OUTPUT_JPEG_QUALITY", 95) or 95))
    q = max(70, min(100, q))
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    return enc.tobytes() if ok else None
